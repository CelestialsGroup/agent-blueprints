//go:build integration

package integration_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/messaging"
	"github.com/shell-echo/agent/internal/persistence"
	"github.com/shell-echo/agent/internal/safety"
)

func TestPostgreSQLRuntimeControlSafetyLedgers(t *testing.T) {
	ctx := context.Background()
	adminDSN := requiredEnv(t, "AGENT_TEST_ADMIN_DSN")
	adminPool := openPool(t, adminDSN, 4)
	createDatabase(t, ctx, adminPool, agentDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, agentDatabase) })

	databaseAdminDSN := replaceDatabase(t, adminDSN, agentDatabase, "postgres", "b021-integration-admin")
	runGoose(t, databaseAdminDSN, "up", true)
	assertMigrationVersion(t, databaseAdminDSN, 3)
	databaseAdminPool := openPool(t, databaseAdminDSN, 4)
	assertControlOutboxBindings(t, ctx, databaseAdminPool)
	assertCanonicalPlatformEventBoundary(t, ctx, databaseAdminPool)
	createApplicationLogin(t, ctx, databaseAdminPool)

	applicationDSN := replaceDatabase(t, adminDSN, agentDatabase, applicationLogin, applicationPass)
	applicationPool := openPool(t, applicationDSN, 16)
	runner, err := persistence.NewTransactionRunner(applicationPool)
	if err != nil {
		t.Fatalf("create transaction runner: %v", err)
	}
	clientRepository, err := persistence.NewClientApplicationRepository(runner)
	if err != nil {
		t.Fatalf("create client repository: %v", err)
	}
	unverifiedControlRepository, err := persistence.NewRuntimeControlRepository(runner)
	if err != nil {
		t.Fatalf("create unverified runtime control repository: %v", err)
	}
	controlRepository, err := persistence.NewRuntimeControlRepository(
		runner,
		persistence.WithSystemSafetyAuthorityVerifier(testSystemSafetyAuthorityVerifier{}),
	)
	if err != nil {
		t.Fatalf("create runtime control repository: %v", err)
	}
	outboxRepository, err := persistence.NewOutboxRepository(runner)
	if err != nil {
		t.Fatalf("create Outbox repository: %v", err)
	}

	baseTime := time.Date(2026, time.July, 27, 0, 0, 0, 0, time.UTC)
	tenantA := tenancy.Tenant{ID: "tenant-a", DisplayName: "Tenant A", CreatedAt: baseTime}
	tenantB := tenancy.Tenant{ID: "tenant-b", DisplayName: "Tenant B", CreatedAt: baseTime}
	registerClient(t, ctx, clientRepository, tenantA, "client-a", baseTime)
	registerClient(t, ctx, clientRepository, tenantB, "client-b", baseTime)
	assertSafetyAuthorityAdmissionACL(t, ctx, applicationPool)
	assertAuthorityBatchBound(t, ctx, controlRepository, tenantA.ID)
	testParentAdmissionLockOrder(t, ctx, controlRepository, tenantA.ID, baseTime)
	testInvocationAdmissionLockOrder(t, ctx, controlRepository, tenantA.ID, baseTime)
	testConcurrentRuntimeCommandConflicts(t, ctx, controlRepository, tenantA.ID, baseTime)
	testFanoutRejectsIncompleteActiveAgentSet(
		t, ctx, controlRepository, outboxRepository, tenantA.ID, baseTime,
	)

	userCommand := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-user-input", WorkOrderID: "work-user", RuntimeRunID: "runtime-root",
		CommandSequence: 1, Type: safety.ActionAppendInput,
		AuthorizedControlRequestID: "control-input", InputID: "input-1",
		InputContentDigest: digestWith("1"), InvocationID: "invocation-user-input",
		InvocationAttemptID: "attempt-user-input", FencingToken: 1,
		IdempotencyKey: "idempotency-user-input", DeadlineAt: baseTime.Add(2 * time.Hour),
		CreatedAt: baseTime.Add(time.Minute),
	})
	childDecisionCommand := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-child-decision", WorkOrderID: "work-user", RuntimeRunID: "runtime-root",
		CommandSequence: 2, Type: safety.ActionSubagentSpawnDecision,
		SpawnRequestID: "spawn-request-1", ChildAdmissionDecisionID: "child-decision-1",
		ChildAdmissionDecisionDigest: digestWith("4"), SpawnOutcome: safety.AdmissionAccepted,
		SpawnReasonCodes: []string{"admitted"}, ChildAgentRunID: "run-child",
		InvocationID: "invocation-child-decision", InvocationAttemptID: "attempt-child-decision",
		FencingToken: 2, IdempotencyKey: "idempotency-child-decision",
		DeadlineAt: baseTime.Add(2 * time.Hour), CreatedAt: baseTime.Add(5 * time.Minute),
	})
	rootCancelCommand := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-cancel-root", WorkOrderID: "work-user", RuntimeRunID: "runtime-root",
		CommandSequence: 3, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-cancel", InvocationID: "invocation-cancel-root",
		InvocationAttemptID: "attempt-cancel-root", FencingToken: 3,
		IdempotencyKey: "idempotency-cancel-root", DeadlineAt: baseTime.Add(2 * time.Hour),
		CreatedAt: baseTime.Add(10 * time.Minute),
	})
	childCancelCommand := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-cancel-child", WorkOrderID: "work-user", RuntimeRunID: "runtime-child",
		CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-cancel", InvocationID: "invocation-cancel-child",
		InvocationAttemptID: "attempt-cancel-child", FencingToken: 1,
		IdempotencyKey: "idempotency-cancel-child", DeadlineAt: baseTime.Add(2 * time.Hour),
		CreatedAt: baseTime.Add(10 * time.Minute),
	})

	admitUserControlAuthorities(
		t, ctx, controlRepository, tenantA.ID, baseTime,
		userCommand, childDecisionCommand, rootCancelCommand, childCancelCommand,
	)
	assertRuntimeCommandOutboxBinding(t, ctx, controlRepository, outboxRepository, tenantA.ID, userCommand)
	insertTerminalAgentRunForLateAdmissionTest(t, ctx, applicationPool, tenantA.ID, baseTime)

	conflictingOutbox := mustControlOutbox(t, "outbox-user-command-rollback", []byte(`{"conflict":true}`), baseTime.Add(time.Minute))
	enqueue(t, ctx, runner, tenantA.ID, conflictingOutbox)
	rollbackOutbox := mustCommandOutbox(t, "outbox-user-command-rollback", userCommand)
	if _, err := controlRepository.AppendRuntimeCommand(ctx, tenantA.ID, userCommand, rollbackOutbox); !errors.Is(err, messaging.ErrOutboxConflict) {
		t.Fatalf("command plus Outbox rollback = %v, want ErrOutboxConflict", err)
	}
	userCommandOutbox := mustCommandOutbox(t, "outbox-user-command", userCommand)
	if outcome, err := controlRepository.AppendRuntimeCommand(ctx, tenantA.ID, userCommand, userCommandOutbox); err != nil || outcome != safety.AppendInserted {
		t.Fatalf("append command after rollback = %s, %v", outcome, err)
	}
	if outcome, err := controlRepository.AppendRuntimeCommand(ctx, tenantA.ID, userCommand, userCommandOutbox); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("replay command = %s, %v", outcome, err)
	}
	if _, err := controlRepository.AppendRuntimeCommand(
		ctx, tenantA.ID, userCommand,
		mustCommandOutbox(t, "outbox-user-command-rebound", userCommand),
	); !errors.Is(err, messaging.ErrOutboxConflict) {
		t.Fatalf("rebind command to another Outbox = %v, want ErrOutboxConflict", err)
	}
	if _, err := outboxRepository.Status(ctx, tenantA.ID, "outbox-user-command-rebound"); !errors.Is(err, messaging.ErrMessagingNotFound) {
		t.Fatalf("conflicting command Outbox persisted = %v, want not found", err)
	}
	if outcome, err := controlRepository.AppendRuntimeCommand(
		ctx, tenantA.ID, childDecisionCommand,
		mustCommandOutbox(t, "outbox-child-decision", childDecisionCommand),
	); err != nil || outcome != safety.AppendInserted {
		t.Fatalf("append child decision command = %s, %v", outcome, err)
	}

	staleCommand := rootCancelCommand
	staleCommand.CommandID = "command-stale-fencing"
	staleCommand.FencingToken = 2
	staleCommand.IdempotencyKey = "idempotency-stale-fencing"
	staleCommand = makeRuntimeCommand(t, staleCommand)
	if _, err := controlRepository.AppendRuntimeCommand(
		ctx, tenantA.ID, staleCommand, mustCommandOutbox(t, "outbox-stale-fencing", staleCommand),
	); !errors.Is(err, safety.ErrStaleFencing) {
		t.Fatalf("stale command fencing = %v", err)
	}
	if _, err := controlRepository.AppendRuntimeCommand(
		ctx, tenantB.ID, rootCancelCommand, mustCommandOutbox(t, "outbox-cross-tenant-command", rootCancelCommand),
	); !errors.Is(err, safety.ErrInvalidAuthority) {
		t.Fatalf("cross-Tenant command = %v, want invalid authority", err)
	}

	userFanout := safety.FanoutSnapshot{
		FanoutID: "fanout-user", FanoutVersion: 1, TenantID: tenantA.ID,
		WorkOrderID: "work-user", Action: safety.ActionCancel,
		AuthorityKind: safety.FanoutUserAuthority, AuthorityID: "control-cancel",
		AuthorityDigest: digestWith("3"),
		Targets: []safety.FanoutTarget{
			{AgentRunID: "run-child", RuntimeRunID: "runtime-child", TargetFencingToken: 1, CommandID: childCancelCommand.CommandID, ControlState: safety.ControlPending},
			{AgentRunID: "run-root", RuntimeRunID: "runtime-root", TargetFencingToken: 3, CommandID: rootCancelCommand.CommandID, ControlState: safety.ControlPending},
		},
		CreatedAt: baseTime.Add(10 * time.Minute), UpdatedAt: baseTime.Add(10 * time.Minute),
	}
	userFanout.FanoutDigest = mustFanoutDigest(t, userFanout)
	userCreation := persistence.FanoutCreation{
		Snapshot: userFanout, ExpectedActiveWorkVersion: 1,
		Dispatch: []persistence.FanoutDispatchTarget{
			{Command: rootCancelCommand, CommandOutbox: mustCommandOutbox(t, "outbox-cancel-root", rootCancelCommand)},
			{Command: childCancelCommand, CommandOutbox: mustCommandOutbox(t, "outbox-cancel-child", childCancelCommand)},
		},
	}
	if outcome, err := controlRepository.CreateFanout(ctx, tenantA.ID, userCreation); err != nil || outcome != safety.AppendInserted {
		t.Fatalf("create user fanout = %s, %v", outcome, err)
	}
	if outcome, err := controlRepository.CreateFanout(ctx, tenantA.ID, userCreation); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("replay user fanout = %s, %v", outcome, err)
	}
	rescheduleOutboxForRetry(
		t, ctx, applicationPool, tenantA.ID, "outbox-cancel-root", baseTime.Add(90*time.Minute),
	)
	if outcome, err := controlRepository.CreateFanout(ctx, tenantA.ID, userCreation); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("replay user fanout after Outbox retry scheduling = %s, %v", outcome, err)
	}
	versionConflict := userCreation
	versionConflict.ExpectedActiveWorkVersion++
	if _, err := controlRepository.CreateFanout(ctx, tenantA.ID, versionConflict); !errors.Is(err, safety.ErrDigestConflict) {
		t.Fatalf("fanout replay with changed active-work CAS = %v, want digest conflict", err)
	}
	if status, err := outboxRepository.Status(ctx, tenantA.ID, "outbox-cancel-root"); err != nil || status.State != messaging.OutboxPending {
		t.Fatalf("fanout command Outbox = %#v, %v", status, err)
	}
	assertDatabaseRejectsLateFanoutAdmissions(t, ctx, applicationPool, tenantA.ID, baseTime)
	if err := controlRepository.AdmitAuthorities(ctx, tenantA.ID, persistence.RuntimeControlAuthorities{
		ChildAdmissions: []safety.ChildAdmissionAuthority{{
			TenantID: tenantA.ID, WorkOrderID: "work-user",
			DecisionID: "decision-late-rejected", DecisionDigest: digestWith("8"),
			SpawnRequestID: "spawn-late-rejected", SpawnRequestDigest: digestWith("9"),
			ParentAgentRunID: "run-root", Outcome: safety.AdmissionRejected,
			ReasonCodes: []string{"work_order_not_active"}, DecidedAt: baseTime.Add(30 * time.Minute),
		}},
	}); err != nil {
		t.Fatalf("persist rejected Child Admission after Fanout closes: %v", err)
	}
	if err := controlRepository.AdmitAuthorities(ctx, tenantA.ID, persistence.RuntimeControlAuthorities{
		AgentRuns: []safety.AgentRunAuthority{{
			TenantID: tenantA.ID, WorkOrderID: "work-user", AgentRunID: "run-root",
			RunKind: "root", RequiredForWorkOrderCompletion: true,
			State: safety.RuntimeRunning, CreatedAt: baseTime,
		}},
	}); err != nil {
		t.Fatalf("replay existing AgentRun after admission closes: %v", err)
	}

	testFanoutLeaseRecovery(t, ctx, controlRepository, tenantA.ID, tenantB.ID)
	reconciledFanout, err := controlRepository.GetFanoutSnapshot(ctx, tenantA.ID, userFanout.FanoutID)
	if err != nil {
		t.Fatalf("reconcile progressed user fanout: %v", err)
	}
	if reconciledFanout.FanoutVersion != 4 || reconciledFanout.PreviousFanoutDigest == "" ||
		len(reconciledFanout.Targets) != len(userFanout.Targets) {
		t.Fatalf("reconciled fanout snapshot = %#v", reconciledFanout)
	}
	if _, err := controlRepository.GetFanoutSnapshot(ctx, tenantB.ID, userFanout.FanoutID); !errors.Is(err, safety.ErrControlNotFound) {
		t.Fatalf("cross-Tenant fanout reconciliation = %v, want not found", err)
	}
	if outcome, err := controlRepository.CreateFanout(ctx, tenantA.ID, userCreation); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("replay progressed user fanout = %s, %v", outcome, err)
	}
	reboundCreation := userCreation
	reboundCreation.Dispatch = append([]persistence.FanoutDispatchTarget(nil), userCreation.Dispatch...)
	reboundCreation.Dispatch[0].CommandOutbox = mustCommandOutbox(t, "outbox-cancel-root-rebound", rootCancelCommand)
	if _, err := controlRepository.CreateFanout(ctx, tenantA.ID, reboundCreation); !errors.Is(err, messaging.ErrOutboxConflict) {
		t.Fatalf("rebind progressed fanout command Outbox = %v, want ErrOutboxConflict", err)
	}
	commandConflict := userCreation
	commandConflict.Snapshot.Targets = append([]safety.FanoutTarget(nil), userCreation.Snapshot.Targets...)
	commandConflict.Snapshot.Targets[0].CommandID, commandConflict.Snapshot.Targets[1].CommandID =
		commandConflict.Snapshot.Targets[1].CommandID, commandConflict.Snapshot.Targets[0].CommandID
	if _, err := controlRepository.CreateFanout(ctx, tenantA.ID, commandConflict); !errors.Is(err, safety.ErrDigestConflict) {
		t.Fatalf("fanout replay with changed internal command binding = %v, want digest conflict", err)
	}
	assertDatabaseRejectsFanoutRegression(t, ctx, applicationPool, tenantA.ID)

	testSystemSafetyFanoutRollback(
		t, ctx, runner, databaseAdminPool, controlRepository, unverifiedControlRepository,
		tenantA.ID, baseTime,
	)
	assertDatabaseRejectsInvalidControlFacts(t, ctx, databaseAdminPool)

	assertPoolTenantContextEmpty(t, ctx, applicationPool)
	downOutput := runGoose(t, databaseAdminDSN, "down", false)
	if !strings.Contains(downOutput, "runtime_control_safety_ledgers contains authoritative data and is forward-only") {
		t.Fatalf("data-bearing B02.3 Down lacks classification: %s", downOutput)
	}
	assertMigrationVersion(t, databaseAdminDSN, 3)
}

func admitUserControlAuthorities(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
	commands ...safety.RuntimeCommand,
) {
	t.Helper()
	authorities := persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{{
			TenantID: tenantID, WorkOrderID: "work-user", State: safety.WorkOrderRunning,
			ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
		}},
		AgentRuns: []safety.AgentRunAuthority{
			{TenantID: tenantID, WorkOrderID: "work-user", AgentRunID: "run-root", RunKind: "root", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
			{TenantID: tenantID, WorkOrderID: "work-user", AgentRunID: "run-child", RunKind: "child", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
		},
		RuntimeRuns: []safety.RuntimeRunAuthority{
			{TenantID: tenantID, WorkOrderID: "work-user", AgentRunID: "run-root", RuntimeRunID: "runtime-root", State: safety.RuntimeRunning, CreatedAt: baseTime},
			{TenantID: tenantID, WorkOrderID: "work-user", AgentRunID: "run-child", RuntimeRunID: "runtime-child", State: safety.RuntimeRunning, CreatedAt: baseTime},
		},
		ControlRequests: []safety.ControlRequestAuthority{
			{TenantID: tenantID, WorkOrderID: "work-user", ControlRequestID: "control-input", RequestDigest: digestWith("2"), Action: safety.ActionAppendInput, ExpectedActiveWorkVersion: 1, Input: &safety.ControlInput{InputID: "input-1", InputMessageID: "message-input-1", ContentDigest: digestWith("1")}, AcceptedAt: baseTime.Add(time.Minute)},
			{TenantID: tenantID, WorkOrderID: "work-user", ControlRequestID: "control-cancel", RequestDigest: digestWith("3"), Action: safety.ActionCancel, ExpectedActiveWorkVersion: 1, AcceptedAt: baseTime.Add(9 * time.Minute)},
		},
		ChildAdmissions: []safety.ChildAdmissionAuthority{{
			TenantID: tenantID, WorkOrderID: "work-user", DecisionID: "child-decision-1",
			DecisionDigest: digestWith("4"), SpawnRequestID: "spawn-request-1",
			SpawnRequestDigest: digestWith("5"), ParentAgentRunID: "run-root",
			Outcome: safety.AdmissionAccepted, ReasonCodes: []string{"admitted"},
			ChildAgentRunID: "run-child", RuntimeRunID: "runtime-child",
			DecidedAt: baseTime.Add(4 * time.Minute),
		}},
	}
	for _, command := range commands {
		authorities.Invocations = append(authorities.Invocations, safety.InvocationAuthority{
			TenantID: tenantID, WorkOrderID: command.WorkOrderID, RuntimeRunID: command.RuntimeRunID,
			InvocationID: command.InvocationID, RequestDigest: command.CommandDigest,
			InvocationAttemptID: command.InvocationAttemptID, AttemptNumber: 1,
			FencingToken:        command.FencingToken,
			InvocationCreatedAt: command.CreatedAt, AttemptCreatedAt: command.CreatedAt,
		})
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, authorities); err != nil {
		t.Fatalf("admit user control authorities: %v", err)
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, authorities); err != nil {
		t.Fatalf("replay user control authorities: %v", err)
	}
	conflictingAttemptTime := authorities.Invocations[0]
	conflictingAttemptTime.AttemptCreatedAt = conflictingAttemptTime.AttemptCreatedAt.Add(time.Second)
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		Invocations: []safety.InvocationAuthority{conflictingAttemptTime},
	}); !errors.Is(err, safety.ErrAuthorityConflict) {
		t.Fatalf("InvocationAttempt replay with changed created_at = %v, want authority conflict", err)
	}
	conflictingInvocationTime := authorities.Invocations[0]
	conflictingInvocationTime.InvocationCreatedAt = conflictingInvocationTime.InvocationCreatedAt.Add(time.Second)
	conflictingInvocationTime.AttemptCreatedAt = conflictingInvocationTime.InvocationCreatedAt
	conflictingInvocationTime.InvocationAttemptID = "attempt-invocation-created-at-conflict"
	conflictingInvocationTime.AttemptNumber = 2
	conflictingInvocationTime.FencingToken = 100
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		Invocations: []safety.InvocationAuthority{conflictingInvocationTime},
	}); !errors.Is(err, safety.ErrAuthorityConflict) {
		t.Fatalf("Invocation replay with changed created_at = %v, want authority conflict", err)
	}
	conflictingRequest := authorities.ControlRequests[0]
	conflictingRequest.Input = &safety.ControlInput{
		InputID: "input-conflict", InputMessageID: "message-input-conflict",
		ContentDigest: conflictingRequest.Input.ContentDigest,
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		ControlRequests: []safety.ControlRequestAuthority{conflictingRequest},
	}); !errors.Is(err, safety.ErrAuthorityConflict) {
		t.Fatalf("ControlRequest replay with changed immutable input = %v, want authority conflict", err)
	}
}

func testFanoutRejectsIncompleteActiveAgentSet(
	t *testing.T,
	ctx context.Context,
	controlRepository *persistence.RuntimeControlRepository,
	outboxRepository *persistence.OutboxRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	command := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-gap-root", WorkOrderID: "work-gap", RuntimeRunID: "runtime-gap-root",
		CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-gap", InvocationID: "invocation-gap-root",
		InvocationAttemptID: "attempt-gap-root", FencingToken: 1,
		IdempotencyKey: "idempotency-gap-root", DeadlineAt: baseTime.Add(2 * time.Hour),
		CreatedAt: baseTime.Add(15 * time.Minute),
	})
	if err := controlRepository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{{
			TenantID: tenantID, WorkOrderID: "work-gap", State: safety.WorkOrderRunning,
			ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
		}},
		AgentRuns: []safety.AgentRunAuthority{
			{TenantID: tenantID, WorkOrderID: "work-gap", AgentRunID: "run-gap-root", RunKind: "root", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
			{TenantID: tenantID, WorkOrderID: "work-gap", AgentRunID: "run-gap-missing-runtime", RunKind: "child", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
		},
		RuntimeRuns: []safety.RuntimeRunAuthority{{
			TenantID: tenantID, WorkOrderID: "work-gap", AgentRunID: "run-gap-root",
			RuntimeRunID: "runtime-gap-root", State: safety.RuntimeRunning, CreatedAt: baseTime,
		}},
		Invocations: []safety.InvocationAuthority{{
			TenantID: tenantID, WorkOrderID: "work-gap", RuntimeRunID: "runtime-gap-root",
			InvocationID: command.InvocationID, RequestDigest: command.CommandDigest,
			InvocationAttemptID: command.InvocationAttemptID, AttemptNumber: 1,
			FencingToken: 1, InvocationCreatedAt: command.CreatedAt, AttemptCreatedAt: command.CreatedAt,
		}},
		ControlRequests: []safety.ControlRequestAuthority{{
			TenantID: tenantID, WorkOrderID: "work-gap", ControlRequestID: "control-gap",
			RequestDigest: digestWith("a"), Action: safety.ActionCancel,
			ExpectedActiveWorkVersion: 1, AcceptedAt: baseTime.Add(14 * time.Minute),
		}},
	}); err != nil {
		t.Fatalf("admit incomplete fanout target authorities: %v", err)
	}
	snapshot := safety.FanoutSnapshot{
		FanoutID: "fanout-gap", FanoutVersion: 1, TenantID: tenantID,
		WorkOrderID: "work-gap", Action: safety.ActionCancel,
		AuthorityKind: safety.FanoutUserAuthority, AuthorityID: "control-gap",
		AuthorityDigest: digestWith("a"),
		Targets: []safety.FanoutTarget{{
			AgentRunID: "run-gap-root", RuntimeRunID: "runtime-gap-root",
			TargetFencingToken: 1, CommandID: command.CommandID, ControlState: safety.ControlPending,
		}},
		CreatedAt: baseTime.Add(15 * time.Minute), UpdatedAt: baseTime.Add(15 * time.Minute),
	}
	snapshot.FanoutDigest = mustFanoutDigest(t, snapshot)
	outbox := mustCommandOutbox(t, "outbox-gap-root", command)
	_, err := controlRepository.CreateFanout(ctx, tenantID, persistence.FanoutCreation{
		Snapshot: snapshot, ExpectedActiveWorkVersion: 1,
		Dispatch: []persistence.FanoutDispatchTarget{{Command: command, CommandOutbox: outbox}},
	})
	if !errors.Is(err, safety.ErrFanoutCoverageConflict) {
		t.Fatalf("fanout with active AgentRun missing RuntimeRun = %v, want coverage conflict", err)
	}
	if _, err := outboxRepository.Status(ctx, tenantID, outbox.MessageID); !errors.Is(err, messaging.ErrMessagingNotFound) {
		t.Fatalf("incomplete fanout Outbox persisted = %v, want not found", err)
	}
	if err := controlRepository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		RuntimeRuns: []safety.RuntimeRunAuthority{{
			TenantID: tenantID, WorkOrderID: "work-gap",
			AgentRunID: "run-gap-missing-runtime", RuntimeRunID: "runtime-gap-recovered",
			State: safety.RuntimeRunning, CreatedAt: baseTime.Add(16 * time.Minute),
		}},
	}); err != nil {
		t.Fatalf("failed fanout did not roll back Child Admission closure: %v", err)
	}
}

func testFanoutLeaseRecovery(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantA, tenantB tenancy.TenantID,
) {
	t.Helper()
	start := make(chan struct{})
	results := make(chan []safety.ClaimedFanoutTarget, 2)
	errorsFound := make(chan error, 2)
	var group sync.WaitGroup
	for _, workerID := range []string{"fanout-worker-a", "fanout-worker-b"} {
		workerID := workerID
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			claimed, err := repository.ClaimFanoutTargets(ctx, tenantA, safety.FanoutClaimRequest{
				WorkerID: workerID, BatchSize: 1, LeaseDuration: 200 * time.Millisecond,
			})
			if err != nil {
				errorsFound <- err
				return
			}
			results <- claimed
		}()
	}
	close(start)
	group.Wait()
	close(results)
	close(errorsFound)
	for err := range errorsFound {
		t.Fatalf("concurrent fanout claim: %v", err)
	}
	var claims []safety.ClaimedFanoutTarget
	for result := range results {
		claims = append(claims, result...)
	}
	if len(claims) != 2 || claims[0].AgentRunID == claims[1].AgentRunID {
		t.Fatalf("fanout concurrent ownership = %#v", claims)
	}
	if err := repository.RenewFanoutTargetLease(ctx, tenantA, claims[0].Lease(), time.Minute); err != nil {
		t.Fatalf("renew first fanout lease: %v", err)
	}
	testConcurrentFanoutProgress(t, ctx, repository, tenantA, claims[0].Lease())
	time.Sleep(300 * time.Millisecond)
	if _, err := repository.ProgressFanoutTarget(ctx, tenantA, claims[1].Lease(), safety.ControlDispatched); !errors.Is(err, safety.ErrFanoutLeaseLost) {
		t.Fatalf("expired fanout progress = %v, want lease lost", err)
	}
	if err := repository.RenewFanoutTargetLease(ctx, tenantB, claims[0].Lease(), time.Minute); !errors.Is(err, safety.ErrFanoutLeaseLost) {
		t.Fatalf("cross-Tenant fanout renew = %v", err)
	}
	recovered, err := repository.ClaimFanoutTargets(ctx, tenantA, safety.FanoutClaimRequest{
		WorkerID: "fanout-worker-recovery", BatchSize: 10, LeaseDuration: time.Minute,
	})
	if err != nil {
		t.Fatalf("recover fanout targets: %v", err)
	}
	if len(recovered) != 2 {
		t.Fatalf("recoverable fanout target count = %d, want 2", len(recovered))
	}
	for _, target := range recovered {
		if target.AgentRunID == claims[1].AgentRunID && target.ClaimFencingToken != claims[1].ClaimFencingToken+1 {
			t.Fatalf("expired lease fencing = %d, want %d", target.ClaimFencingToken, claims[1].ClaimFencingToken+1)
		}
		next := safety.ControlConfirmed
		if target.ControlState == safety.ControlPending {
			next = safety.ControlOutcomeUnknown
		}
		if _, err := repository.ProgressFanoutTarget(ctx, tenantA, target.Lease(), next); err != nil {
			t.Fatalf("reconcile fanout target %s: %v", target.AgentRunID, err)
		}
	}
	if _, err := repository.ClaimFanoutTargets(ctx, tenantB, safety.FanoutClaimRequest{
		WorkerID: "tenant-b-worker", BatchSize: 10, LeaseDuration: time.Minute,
	}); err != nil {
		t.Fatalf("Tenant B fanout claim: %v", err)
	}
	if _, err := repository.ProgressFanoutTarget(ctx, tenantA, claims[1].Lease(), safety.ControlConfirmed); !errors.Is(err, safety.ErrFanoutLeaseLost) {
		t.Fatalf("stale recovered lease progress = %v", err)
	}
}

func testConcurrentFanoutProgress(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	lease safety.FanoutLease,
) {
	t.Helper()
	start := make(chan struct{})
	results := make(chan error, 2)
	var group sync.WaitGroup
	for range 2 {
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			_, err := repository.ProgressFanoutTarget(ctx, tenantID, lease, safety.ControlDispatched)
			results <- err
		}()
	}
	close(start)
	group.Wait()
	close(results)
	progressed, fenced := 0, 0
	for err := range results {
		switch {
		case err == nil:
			progressed++
		case errors.Is(err, safety.ErrFanoutLeaseLost):
			fenced++
		default:
			t.Fatalf("concurrent fanout progress = %v", err)
		}
	}
	if progressed != 1 || fenced != 1 {
		t.Fatalf("concurrent fanout progress outcomes: progressed=%d fenced=%d", progressed, fenced)
	}
}

func testSystemSafetyFanoutRollback(
	t *testing.T,
	ctx context.Context,
	runner *persistence.TransactionRunner,
	adminPool *pgxpool.Pool,
	repository *persistence.RuntimeControlRepository,
	unverifiedRepository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	control := safety.SystemSafetyControl{
		SafetyControlID: "safety-system", TenantID: tenantID, WorkOrderID: "work-system",
		RuntimeRunID: "runtime-system", Action: safety.ActionCancel,
		Reason:             safety.ReasonCommercialAuthorizationExpired,
		EvidenceContractID: "urn:agent-platform:runtime-authorization:v1",
		EvidenceID:         "evidence-system", EvidenceDigest: digestWith("6"),
		ObservedAt: baseTime.Add(20 * time.Minute), IssuerSubjectID: "safety-controller",
		IssuedAt: baseTime.Add(22 * time.Minute),
	}
	control.ControlDigest = mustSafetyDigest(t, control)
	command := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-system", WorkOrderID: "work-system", RuntimeRunID: "runtime-system",
		CommandSequence: 1, Type: safety.ActionCancel, SystemSafetyControlID: control.SafetyControlID,
		SystemSafetyControlDigest: control.ControlDigest, InvocationID: "invocation-system",
		InvocationAttemptID: "attempt-system", FencingToken: 1,
		IdempotencyKey: "idempotency-system-cancel", DeadlineAt: baseTime.Add(3 * time.Hour),
		CreatedAt: baseTime.Add(22 * time.Minute),
	})
	authorities := persistence.RuntimeControlAuthorities{
		WorkOrders:  []safety.WorkOrderAuthority{{TenantID: tenantID, WorkOrderID: "work-system", State: safety.WorkOrderRunning, ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime}},
		AgentRuns:   []safety.AgentRunAuthority{{TenantID: tenantID, WorkOrderID: "work-system", AgentRunID: "run-system", RunKind: "root", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime}},
		RuntimeRuns: []safety.RuntimeRunAuthority{{TenantID: tenantID, WorkOrderID: "work-system", AgentRunID: "run-system", RuntimeRunID: "runtime-system", State: safety.RuntimeRunning, CreatedAt: baseTime}},
		Invocations: []safety.InvocationAuthority{{
			TenantID: tenantID, WorkOrderID: "work-system", RuntimeRunID: "runtime-system",
			InvocationID: command.InvocationID, RequestDigest: command.CommandDigest,
			InvocationAttemptID: command.InvocationAttemptID, AttemptNumber: 1, FencingToken: 1,
			InvocationCreatedAt: command.CreatedAt, AttemptCreatedAt: command.CreatedAt,
		}},
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, authorities); err != nil {
		t.Fatalf("admit system safety authorities: %v", err)
	}
	controlOutbox := controlOutboxPointer(t, "outbox-system-control-unverified", control)
	if _, err := unverifiedRepository.AppendSystemSafetyControl(
		ctx, tenantID, control, *controlOutbox,
	); !errors.Is(err, safety.ErrSafetyAuthorityUnverified) {
		t.Fatalf("unverified SystemSafetyControl authority = %v, want fail-closed", err)
	}
	wrongIssuer := control
	wrongIssuer.IssuerSubjectID = "different-controller"
	wrongIssuer.ControlDigest = mustSafetyDigest(t, wrongIssuer)
	if _, err := repository.AppendSystemSafetyControl(
		ctx, tenantID, wrongIssuer,
		*controlOutboxPointer(t, "outbox-system-control-wrong-issuer", wrongIssuer),
	); !errors.Is(err, safety.ErrSafetyAuthorityUnverified) {
		t.Fatalf("mismatched authenticated Safety Controller = %v, want fail-closed", err)
	}
	wrongEvidenceProfile := control
	wrongEvidenceProfile.Reason = safety.ReasonOperatorEmergencyStop
	wrongEvidenceProfile.Action = safety.ActionPause
	wrongEvidenceProfile.ControlDigest = mustSafetyDigest(t, wrongEvidenceProfile)
	if _, err := repository.AppendSystemSafetyControl(
		ctx, tenantID, wrongEvidenceProfile,
		*controlOutboxPointer(t, "outbox-system-control-wrong-evidence", wrongEvidenceProfile),
	); !errors.Is(err, safety.ErrSafetyAuthorityUnverified) {
		t.Fatalf("unmapped safety reason/evidence profile = %v, want fail-closed", err)
	}
	seedSystemSafetyAuthorities(t, ctx, adminPool, tenantID, control, baseTime)
	assertSafetyControlOutboxBinding(t, ctx, repository, tenantID, control)
	snapshot := safety.FanoutSnapshot{
		FanoutID: "fanout-system", FanoutVersion: 1, TenantID: tenantID,
		WorkOrderID: "work-system", Action: safety.ActionCancel,
		AuthorityKind: safety.FanoutSystemAuthority, AuthorityID: control.EvidenceID,
		AuthorityDigest: control.EvidenceDigest, SafetyEvidenceContractID: control.EvidenceContractID,
		Targets:   []safety.FanoutTarget{{AgentRunID: "run-system", RuntimeRunID: "runtime-system", TargetFencingToken: 1, SystemSafetyControlID: control.SafetyControlID, SystemSafetyControlDigest: control.ControlDigest, CommandID: command.CommandID, ControlState: safety.ControlPending}},
		CreatedAt: baseTime.Add(22 * time.Minute), UpdatedAt: baseTime.Add(22 * time.Minute),
	}
	snapshot.FanoutDigest = mustFanoutDigest(t, snapshot)
	conflict := mustControlOutbox(t, "outbox-system-control-rollback", []byte(`{"conflict":true}`), control.IssuedAt)
	enqueue(t, ctx, runner, tenantID, conflict)
	creation := persistence.FanoutCreation{
		Snapshot: snapshot, ExpectedActiveWorkVersion: 1,
		Dispatch: []persistence.FanoutDispatchTarget{{
			Command: command, CommandOutbox: mustCommandOutbox(t, "outbox-system-command", command),
			SystemSafetyControl: &control,
			SafetyControlOutbox: controlOutboxPointer(t, "outbox-system-control-rollback", control),
		}},
	}
	if _, err := repository.CreateFanout(ctx, tenantID, creation); !errors.Is(err, messaging.ErrOutboxConflict) {
		t.Fatalf("system control/Fanout rollback = %v", err)
	}
	creation.Dispatch[0].SafetyControlOutbox = controlOutboxPointer(t, "outbox-system-control", control)
	if outcome, err := repository.CreateFanout(ctx, tenantID, creation); err != nil || outcome != safety.AppendInserted {
		t.Fatalf("system control/Fanout after rollback = %s, %v", outcome, err)
	}
	if outcome, err := repository.CreateFanout(ctx, tenantID, creation); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("system control/Fanout replay = %s, %v", outcome, err)
	}
	duplicateCommand := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-system-duplicate-control", WorkOrderID: control.WorkOrderID,
		RuntimeRunID: control.RuntimeRunID, CommandSequence: 2, Type: safety.ActionCancel,
		SystemSafetyControlID: control.SafetyControlID, SystemSafetyControlDigest: control.ControlDigest,
		InvocationID:        "invocation-system-duplicate-control",
		InvocationAttemptID: "attempt-system-duplicate-control", FencingToken: 2,
		IdempotencyKey: "idempotency-system-duplicate-control",
		DeadlineAt:     baseTime.Add(3 * time.Hour), CreatedAt: baseTime.Add(23 * time.Minute),
	})
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		Invocations: []safety.InvocationAuthority{{
			TenantID: tenantID, WorkOrderID: control.WorkOrderID, RuntimeRunID: control.RuntimeRunID,
			InvocationID: duplicateCommand.InvocationID, RequestDigest: duplicateCommand.CommandDigest,
			InvocationAttemptID: duplicateCommand.InvocationAttemptID, AttemptNumber: 1, FencingToken: 2,
			InvocationCreatedAt: duplicateCommand.CreatedAt, AttemptCreatedAt: duplicateCommand.CreatedAt,
		}},
	}); err != nil {
		t.Fatalf("admit duplicate-control command Invocation: %v", err)
	}
	if _, err := repository.AppendRuntimeCommand(
		ctx, tenantID, duplicateCommand,
		mustCommandOutbox(t, "outbox-system-duplicate-control", duplicateCommand),
	); !errors.Is(err, safety.ErrDigestConflict) {
		t.Fatalf("second command for one SystemSafetyControl = %v, want digest conflict", err)
	}
	if outcome, err := repository.AppendSystemSafetyControl(
		ctx, tenantID, control, *creation.Dispatch[0].SafetyControlOutbox,
	); err != nil || outcome != safety.AppendReplay {
		t.Fatalf("SystemSafetyControl ID/digest replay = %s, %v", outcome, err)
	}
	if _, err := repository.AppendSystemSafetyControl(
		ctx, tenantID, control,
		*controlOutboxPointer(t, "outbox-system-control-rebound", control),
	); !errors.Is(err, messaging.ErrOutboxConflict) {
		t.Fatalf("rebind SystemSafetyControl Outbox = %v, want ErrOutboxConflict", err)
	}
	conflictingControl := control
	conflictingControl.IssuedAt = conflictingControl.IssuedAt.Add(time.Second)
	conflictingControl.ControlDigest = mustSafetyDigest(t, conflictingControl)
	if _, err := repository.AppendSystemSafetyControl(
		ctx, tenantID, conflictingControl,
		*controlOutboxPointer(t, "outbox-system-control-conflict", conflictingControl),
	); !errors.Is(err, safety.ErrDigestConflict) {
		t.Fatalf("SystemSafetyControl same ID with different digest = %v", err)
	}
}

func assertDatabaseRejectsFanoutRegression(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
) {
	t.Helper()
	err := persistenceRunSQL(ctx, pool, tenantID, `
		UPDATE agent.agent_run_control_fanout_targets
		SET control_state = 'pending', updated_at = clock_timestamp()
		WHERE fanout_id = 'fanout-user'
		  AND control_state IN ('confirmed', 'outcome_unknown')
	`)
	if err == nil {
		t.Fatal("database accepted a fanout state regression")
	}
}

func assertDatabaseRejectsLateFanoutAdmissions(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	checks := []struct {
		name      string
		query     string
		arguments []any
	}{
		{
			name: "AgentRun after Fanout admission close",
			query: `INSERT INTO agent.agent_runs (
			            tenant_id, work_order_id, agent_run_id, run_kind,
			            required_for_work_order_completion, state, created_at, updated_at
			        ) VALUES (
			            $2, 'work-user', 'run-late', 'child', true,
			            'running', $1, $1
			        )`,
			arguments: []any{baseTime.Add(30 * time.Minute), string(tenantID)},
		},
		{
			name: "RuntimeRun after Fanout admission close",
			query: `INSERT INTO agent.agent_runtime_runs (
			            tenant_id, work_order_id, agent_run_id, runtime_run_id,
			            state, created_at, updated_at
			        ) VALUES (
			            $2, 'work-user', 'run-terminal', 'runtime-late',
			            'running', $1, $1
			        )`,
			arguments: []any{baseTime.Add(30 * time.Minute), string(tenantID)},
		},
		{
			name: "accepted Child Admission decision after Fanout admission close",
			query: `INSERT INTO agent.child_agent_run_admission_decisions (
			            tenant_id, work_order_id, decision_id, decision_digest,
			            spawn_request_id, spawn_request_digest, parent_agent_run_id,
			            outcome, reason_codes, child_agent_run_id, runtime_run_id, decided_at
			        ) VALUES (
			            $4, 'work-user', 'decision-late-accepted', $2,
			            'spawn-late-accepted', $3, 'run-root', 'accepted',
			            ARRAY['admitted']::varchar[], 'run-child', 'runtime-child', $1
			        )`,
			arguments: []any{
				baseTime.Add(30 * time.Minute), digestWith("8"), digestWith("9"), string(tenantID),
			},
		},
	}
	for _, check := range checks {
		err := persistenceRunSQLArgs(ctx, pool, tenantID, check.query, check.arguments...)
		var databaseError *pgconn.PgError
		if !errors.As(err, &databaseError) || databaseError.Code != "23514" {
			t.Fatalf("database %s rejection = %v, want SQLSTATE 23514", check.name, err)
		}
	}
}

func insertTerminalAgentRunForLateAdmissionTest(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin terminal AgentRun seed transaction: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", string(tenantID)); err != nil {
		t.Fatalf("set terminal AgentRun TenantContext: %v", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO agent.agent_runs (
		    tenant_id, work_order_id, agent_run_id, run_kind,
		    required_for_work_order_completion, state, created_at, updated_at
		) VALUES ($1, 'work-user', 'run-terminal', 'child', false, 'succeeded', $2, $2)
	`, string(tenantID), baseTime); err != nil {
		t.Fatalf("insert terminal AgentRun for late-admission test: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit terminal AgentRun for late-admission test: %v", err)
	}
}

func assertControlOutboxBindings(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) {
	t.Helper()
	type constraintExpectation struct {
		name              string
		kind              string
		deferrable        bool
		deferred          bool
		requiredFragments []string
	}
	expected := map[string]constraintExpectation{
		"outbox_messages_control_delivery_binding_uk": {
			name: "outbox_messages_control_delivery_binding_uk", kind: "u",
			requiredFragments: []string{"destination", "initial_available_at", "created_at"},
		},
		"system_safety_controls_outbox_fk": {
			name: "system_safety_controls_outbox_fk", kind: "f", deferrable: true, deferred: true,
			requiredFragments: []string{"outbox_destination", "outbox_available_at", "outbox_created_at", "initial_available_at"},
		},
		"agent_runtime_commands_outbox_fk": {
			name: "agent_runtime_commands_outbox_fk", kind: "f", deferrable: true, deferred: true,
			requiredFragments: []string{"outbox_destination", "outbox_available_at", "outbox_created_at", "initial_available_at"},
		},
		"system_safety_controls_outbox_uk": {
			name: "system_safety_controls_outbox_uk", kind: "u",
		},
		"agent_runtime_commands_outbox_uk": {
			name: "agent_runtime_commands_outbox_uk", kind: "u",
		},
	}
	rows, err := pool.Query(ctx, `
		SELECT constraint_name, constraint_type::text, condeferrable, condeferred,
		       constraint_definition
		FROM (
			SELECT c.conname AS constraint_name,
			       c.contype AS constraint_type,
			       c.condeferrable,
			       c.condeferred,
			       pg_get_constraintdef(c.oid) AS constraint_definition
			FROM pg_constraint AS c
			JOIN pg_class AS relation ON relation.oid = c.conrelid
			JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
			WHERE namespace.nspname = 'agent'
			  AND c.conname = ANY($1::text[])
		) AS bindings
		ORDER BY constraint_name
		`, []string{
		"outbox_messages_control_delivery_binding_uk",
		"system_safety_controls_outbox_fk", "agent_runtime_commands_outbox_fk",
		"system_safety_controls_outbox_uk", "agent_runtime_commands_outbox_uk",
	})
	if err != nil {
		t.Fatalf("read command/control Outbox constraints: %v", err)
	}
	defer rows.Close()
	seen := 0
	for rows.Next() {
		var name, kind, definition string
		var deferrable, deferred bool
		if err := rows.Scan(&name, &kind, &deferrable, &deferred, &definition); err != nil {
			t.Fatalf("scan command/control Outbox constraint: %v", err)
		}
		want, exists := expected[name]
		if !exists || kind != want.kind || deferrable != want.deferrable || deferred != want.deferred {
			t.Fatalf("unexpected command/control Outbox constraint %q: kind=%s deferrable=%t deferred=%t", name, kind, deferrable, deferred)
		}
		for _, fragment := range want.requiredFragments {
			if !strings.Contains(definition, fragment) {
				t.Fatalf("command/control Outbox constraint %q lacks %q: %s", name, fragment, definition)
			}
		}
		seen++
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate command/control Outbox constraints: %v", err)
	}
	if seen != len(expected) {
		t.Fatalf("command/control Outbox constraint count = %d, want %d", seen, len(expected))
	}
}

func assertCanonicalPlatformEventBoundary(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) {
	t.Helper()
	var canonicalEventsAbsent, replacementEventsAbsent bool
	if err := pool.QueryRow(ctx, `
		SELECT to_regclass('agent.canonical_events') IS NULL,
		       to_regclass('agent.platform_events') IS NULL
	`).Scan(&canonicalEventsAbsent, &replacementEventsAbsent); err != nil {
		t.Fatalf("read Canonical Platform Event persistence boundary: %v", err)
	}
	if !canonicalEventsAbsent || !replacementEventsAbsent {
		t.Fatal("B02.3 must not invent Canonical or internal Platform Event persistence")
	}
}

type testSystemSafetyAuthorityVerifier struct{}

func (testSystemSafetyAuthorityVerifier) VerifySystemSafetyAuthority(
	ctx context.Context,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if tenantID != control.TenantID || control.IssuerSubjectID != "safety-controller" ||
		control.Reason != safety.ReasonCommercialAuthorizationExpired ||
		control.EvidenceContractID != "urn:agent-platform:runtime-authorization:v1" {
		return errors.New("test authority does not match the authenticated issuer and evidence profile")
	}
	return nil
}

func assertSafetyAuthorityAdmissionACL(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) {
	t.Helper()
	var canInsertController, canInsertEvidence bool
	if err := pool.QueryRow(ctx, `
		SELECT has_any_column_privilege(
		           current_user, 'agent.platform_safety_controllers', 'INSERT'
		       ),
		       has_any_column_privilege(
		           current_user, 'agent.safety_trigger_evidence', 'INSERT'
		       )
	`).Scan(&canInsertController, &canInsertEvidence); err != nil {
		t.Fatalf("read safety authority admission ACL: %v", err)
	}
	if canInsertController || canInsertEvidence {
		t.Fatalf("Application role can admit safety authority: controller=%t evidence=%t", canInsertController, canInsertEvidence)
	}
}

func assertAuthorityBatchBound(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
) {
	t.Helper()
	overflow := persistence.RuntimeControlAuthorities{
		WorkOrders: make([]safety.WorkOrderAuthority, persistence.MaxRuntimeControlAuthorityBatch+1),
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, overflow); !errors.Is(err, safety.ErrInvalidAuthority) {
		t.Fatalf("oversized authority batch = %v, want invalid authority", err)
	}
}

func testInvocationAdmissionLockOrder(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	invocationCreatedAt := baseTime.Add(30 * time.Minute)
	initial := persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{{
			TenantID: tenantID, WorkOrderID: "work-invocation-order", State: safety.WorkOrderRunning,
			ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
		}},
		AgentRuns: []safety.AgentRunAuthority{{
			TenantID: tenantID, WorkOrderID: "work-invocation-order", AgentRunID: "run-invocation-order",
			RunKind: "root", RequiredForWorkOrderCompletion: true,
			State: safety.RuntimeRunning, CreatedAt: baseTime,
		}},
		RuntimeRuns: []safety.RuntimeRunAuthority{{
			TenantID: tenantID, WorkOrderID: "work-invocation-order", AgentRunID: "run-invocation-order",
			RuntimeRunID: "runtime-invocation-order", State: safety.RuntimeRunning, CreatedAt: baseTime,
		}},
		Invocations: []safety.InvocationAuthority{
			{
				TenantID: tenantID, WorkOrderID: "work-invocation-order", RuntimeRunID: "runtime-invocation-order",
				InvocationID: "invocation-order-a", RequestDigest: digestWith("a"),
				InvocationAttemptID: "attempt-order-a-1", AttemptNumber: 1, FencingToken: 1,
				InvocationCreatedAt: invocationCreatedAt, AttemptCreatedAt: invocationCreatedAt,
			},
			{
				TenantID: tenantID, WorkOrderID: "work-invocation-order", RuntimeRunID: "runtime-invocation-order",
				InvocationID: "invocation-order-b", RequestDigest: digestWith("b"),
				InvocationAttemptID: "attempt-order-b-1", AttemptNumber: 1, FencingToken: 2,
				InvocationCreatedAt: invocationCreatedAt, AttemptCreatedAt: invocationCreatedAt,
			},
		},
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, initial); err != nil {
		t.Fatalf("admit invocation lock-order parents: %v", err)
	}
	attemptCreatedAt := invocationCreatedAt.Add(time.Minute)
	a := safety.InvocationAuthority{
		TenantID: tenantID, WorkOrderID: "work-invocation-order", RuntimeRunID: "runtime-invocation-order",
		InvocationID: "invocation-order-a", RequestDigest: digestWith("a"),
		InvocationAttemptID: "attempt-order-a-2", AttemptNumber: 2, FencingToken: 3,
		InvocationCreatedAt: invocationCreatedAt, AttemptCreatedAt: attemptCreatedAt,
	}
	b := safety.InvocationAuthority{
		TenantID: tenantID, WorkOrderID: "work-invocation-order", RuntimeRunID: "runtime-invocation-order",
		InvocationID: "invocation-order-b", RequestDigest: digestWith("b"),
		InvocationAttemptID: "attempt-order-b-2", AttemptNumber: 2, FencingToken: 4,
		InvocationCreatedAt: invocationCreatedAt, AttemptCreatedAt: attemptCreatedAt,
	}
	batches := [][]safety.InvocationAuthority{{a, b}, {b, a}}
	start := make(chan struct{})
	errorsFound := make(chan error, len(batches))
	var group sync.WaitGroup
	concurrentCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	for _, batch := range batches {
		batch := batch
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			errorsFound <- repository.AdmitAuthorities(
				concurrentCtx, tenantID, persistence.RuntimeControlAuthorities{Invocations: batch},
			)
		}()
	}
	close(start)
	group.Wait()
	close(errorsFound)
	for err := range errorsFound {
		if err != nil {
			t.Fatalf("opposite-order Invocation admission: %v", err)
		}
	}
	if batches[1][0].InvocationID != b.InvocationID || batches[1][1].InvocationID != a.InvocationID {
		t.Fatal("authority normalization mutated caller-owned Invocation order")
	}
}

func testParentAdmissionLockOrder(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	parents := persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{
			{
				TenantID: tenantID, WorkOrderID: "work-parent-order-a", State: safety.WorkOrderRunning,
				ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
			},
			{
				TenantID: tenantID, WorkOrderID: "work-parent-order-b", State: safety.WorkOrderRunning,
				ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
			},
		},
		AgentRuns: []safety.AgentRunAuthority{
			{
				TenantID: tenantID, WorkOrderID: "work-parent-order-a", AgentRunID: "run-parent-existing-a",
				RunKind: "root", RequiredForWorkOrderCompletion: true,
				State: safety.RuntimeRunning, CreatedAt: baseTime,
			},
			{
				TenantID: tenantID, WorkOrderID: "work-parent-order-b", AgentRunID: "run-parent-existing-b",
				RunKind: "root", RequiredForWorkOrderCompletion: true,
				State: safety.RuntimeRunning, CreatedAt: baseTime,
			},
		},
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, parents); err != nil {
		t.Fatalf("admit parent lock-order WorkOrders: %v", err)
	}

	batches := []persistence.RuntimeControlAuthorities{
		{
			AgentRuns: []safety.AgentRunAuthority{{
				TenantID: tenantID, WorkOrderID: "work-parent-order-b", AgentRunID: "run-parent-order-a",
				RunKind: "root", RequiredForWorkOrderCompletion: true,
				State: safety.RuntimeRunning, CreatedAt: baseTime,
			}},
			RuntimeRuns: []safety.RuntimeRunAuthority{{
				TenantID: tenantID, WorkOrderID: "work-parent-order-a", AgentRunID: "run-parent-existing-a",
				RuntimeRunID: "runtime-parent-order-a", State: safety.RuntimeRunning, CreatedAt: baseTime,
			}},
		},
		{
			AgentRuns: []safety.AgentRunAuthority{{
				TenantID: tenantID, WorkOrderID: "work-parent-order-a", AgentRunID: "run-parent-order-b",
				RunKind: "root", RequiredForWorkOrderCompletion: true,
				State: safety.RuntimeRunning, CreatedAt: baseTime,
			}},
			RuntimeRuns: []safety.RuntimeRunAuthority{{
				TenantID: tenantID, WorkOrderID: "work-parent-order-b", AgentRunID: "run-parent-existing-b",
				RuntimeRunID: "runtime-parent-order-b", State: safety.RuntimeRunning, CreatedAt: baseTime,
			}},
		},
	}
	start := make(chan struct{})
	errorsFound := make(chan error, len(batches))
	var group sync.WaitGroup
	concurrentCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	for _, batch := range batches {
		batch := batch
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			errorsFound <- repository.AdmitAuthorities(concurrentCtx, tenantID, batch)
		}()
	}
	close(start)
	group.Wait()
	close(errorsFound)
	for err := range errorsFound {
		if err != nil {
			t.Fatalf("opposite cross-category parent admission: %v", err)
		}
	}
	if batches[0].AgentRuns[0].WorkOrderID != "work-parent-order-b" ||
		batches[0].RuntimeRuns[0].WorkOrderID != "work-parent-order-a" {
		t.Fatal("authority normalization mutated caller-owned cross-category order")
	}
}

func testConcurrentRuntimeCommandConflicts(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	createdAt := baseTime.Add(35 * time.Minute)
	sequenceLeft := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-race-sequence-left", WorkOrderID: "work-command-race",
		RuntimeRunID: "runtime-command-race-sequence", CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-command-race-sequence",
		InvocationID:               "invocation-race-sequence-left", InvocationAttemptID: "attempt-race-sequence-left",
		FencingToken: 1, IdempotencyKey: "idempotency-race-sequence-left",
		DeadlineAt: baseTime.Add(3 * time.Hour), CreatedAt: createdAt,
	})
	sequenceRight := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-race-sequence-right", WorkOrderID: "work-command-race",
		RuntimeRunID: "runtime-command-race-sequence", CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-command-race-sequence",
		InvocationID:               "invocation-race-sequence-right", InvocationAttemptID: "attempt-race-sequence-right",
		FencingToken: 2, IdempotencyKey: "idempotency-race-sequence-right",
		DeadlineAt: baseTime.Add(3 * time.Hour), CreatedAt: createdAt,
	})
	digestLeft := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-race-digest", WorkOrderID: "work-command-race",
		RuntimeRunID: "runtime-command-race-digest", CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-command-race-digest", Reason: "left",
		InvocationID: "invocation-race-digest-left", InvocationAttemptID: "attempt-race-digest-left",
		FencingToken: 1, IdempotencyKey: "idempotency-race-digest-left",
		DeadlineAt: baseTime.Add(3 * time.Hour), CreatedAt: createdAt,
	})
	digestRight := makeRuntimeCommand(t, safety.RuntimeCommand{
		CommandID: "command-race-digest", WorkOrderID: "work-command-race",
		RuntimeRunID: "runtime-command-race-digest", CommandSequence: 1, Type: safety.ActionCancel,
		AuthorizedControlRequestID: "control-command-race-digest", Reason: "right",
		InvocationID: "invocation-race-digest-right", InvocationAttemptID: "attempt-race-digest-right",
		FencingToken: 2, IdempotencyKey: "idempotency-race-digest-right",
		DeadlineAt: baseTime.Add(3 * time.Hour), CreatedAt: createdAt,
	})
	commands := []safety.RuntimeCommand{sequenceLeft, sequenceRight, digestLeft, digestRight}
	authorities := persistence.RuntimeControlAuthorities{
		WorkOrders: []safety.WorkOrderAuthority{{
			TenantID: tenantID, WorkOrderID: "work-command-race", State: safety.WorkOrderRunning,
			ActiveWorkVersion: 1, ChildAdmissionOpen: true, CreatedAt: baseTime,
		}},
		AgentRuns: []safety.AgentRunAuthority{
			{TenantID: tenantID, WorkOrderID: "work-command-race", AgentRunID: "run-command-race-sequence", RunKind: "root", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
			{TenantID: tenantID, WorkOrderID: "work-command-race", AgentRunID: "run-command-race-digest", RunKind: "child", RequiredForWorkOrderCompletion: true, State: safety.RuntimeRunning, CreatedAt: baseTime},
		},
		RuntimeRuns: []safety.RuntimeRunAuthority{
			{TenantID: tenantID, WorkOrderID: "work-command-race", AgentRunID: "run-command-race-sequence", RuntimeRunID: "runtime-command-race-sequence", State: safety.RuntimeRunning, CreatedAt: baseTime},
			{TenantID: tenantID, WorkOrderID: "work-command-race", AgentRunID: "run-command-race-digest", RuntimeRunID: "runtime-command-race-digest", State: safety.RuntimeRunning, CreatedAt: baseTime},
		},
		ControlRequests: []safety.ControlRequestAuthority{
			{TenantID: tenantID, WorkOrderID: "work-command-race", ControlRequestID: "control-command-race-sequence", RequestDigest: digestWith("c"), Action: safety.ActionCancel, ExpectedActiveWorkVersion: 1, AcceptedAt: createdAt.Add(-time.Minute)},
			{TenantID: tenantID, WorkOrderID: "work-command-race", ControlRequestID: "control-command-race-digest", RequestDigest: digestWith("d"), Action: safety.ActionCancel, ExpectedActiveWorkVersion: 1, AcceptedAt: createdAt.Add(-time.Minute)},
		},
	}
	for _, command := range commands {
		authorities.Invocations = append(authorities.Invocations, safety.InvocationAuthority{
			TenantID: tenantID, WorkOrderID: command.WorkOrderID, RuntimeRunID: command.RuntimeRunID,
			InvocationID: command.InvocationID, RequestDigest: command.CommandDigest,
			InvocationAttemptID: command.InvocationAttemptID, AttemptNumber: 1,
			FencingToken:        command.FencingToken,
			InvocationCreatedAt: command.CreatedAt, AttemptCreatedAt: command.CreatedAt,
		})
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, authorities); err != nil {
		t.Fatalf("admit concurrent command authorities: %v", err)
	}
	assertConcurrentCommandPair(
		t, ctx, repository, tenantID, []safety.RuntimeCommand{sequenceLeft, sequenceRight},
		safety.ErrSequenceConflict,
	)
	assertConcurrentCommandPair(
		t, ctx, repository, tenantID, []safety.RuntimeCommand{digestLeft, digestRight},
		safety.ErrDigestConflict,
	)
}

func assertConcurrentCommandPair(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	commands []safety.RuntimeCommand,
	wantConflict error,
) {
	t.Helper()
	start := make(chan struct{})
	results := make(chan error, len(commands))
	messages := make([]messaging.OutboundMessage, len(commands))
	for index, command := range commands {
		messages[index] = mustCommandOutbox(
			t, fmt.Sprintf("outbox-command-race-%s-%d", command.CommandID, index), command,
		)
	}
	var group sync.WaitGroup
	for index, command := range commands {
		index, command := index, command
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			outcome, err := repository.AppendRuntimeCommand(
				ctx, tenantID, command, messages[index],
			)
			if err == nil && outcome != safety.AppendInserted {
				err = fmt.Errorf("unexpected command race outcome %q", outcome)
			}
			results <- err
		}()
	}
	close(start)
	group.Wait()
	close(results)
	inserted, conflicted := 0, 0
	for err := range results {
		switch {
		case err == nil:
			inserted++
		case errors.Is(err, wantConflict):
			conflicted++
		default:
			t.Fatalf("concurrent command result = %v", err)
		}
	}
	if inserted != 1 || conflicted != 1 {
		t.Fatalf("concurrent command outcomes: inserted=%d conflicted=%d", inserted, conflicted)
	}
}

func assertRuntimeCommandOutboxBinding(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	outboxRepository *persistence.OutboxRepository,
	tenantID tenancy.TenantID,
	command safety.RuntimeCommand,
) {
	t.Helper()
	payload, err := command.Payload()
	if err != nil {
		t.Fatalf("encode runtime command for Outbox binding checks: %v", err)
	}
	cases := []struct {
		name        string
		messageID   string
		destination string
		availableAt time.Time
		createdAt   time.Time
	}{
		{name: "wrong destination", messageID: "outbox-command-wrong-destination", destination: "untrusted-consumer", availableAt: command.CreatedAt, createdAt: command.CreatedAt},
		{name: "delayed availability", messageID: "outbox-command-delayed", destination: "agent-runtime-control", availableAt: command.CreatedAt.Add(time.Second), createdAt: command.CreatedAt},
		{name: "shifted creation", messageID: "outbox-command-shifted", destination: "agent-runtime-control", availableAt: command.CreatedAt.Add(time.Second), createdAt: command.CreatedAt.Add(time.Second)},
	}
	for _, check := range cases {
		message, err := messaging.NewOutboundMessage(
			check.messageID, check.destination, payload, check.availableAt, check.createdAt,
		)
		if err != nil {
			t.Fatalf("construct %s Outbox probe: %v", check.name, err)
		}
		if _, err := repository.AppendRuntimeCommand(ctx, tenantID, command, message); !errors.Is(err, messaging.ErrOutboxConflict) {
			t.Fatalf("runtime command %s Outbox = %v, want conflict", check.name, err)
		}
		if _, err := outboxRepository.Status(ctx, tenantID, message.MessageID); !errors.Is(err, messaging.ErrMessagingNotFound) {
			t.Fatalf("runtime command %s Outbox persisted = %v", check.name, err)
		}
	}
}

func assertSafetyControlOutboxBinding(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
) {
	t.Helper()
	payload, err := control.Payload()
	if err != nil {
		t.Fatalf("encode SystemSafetyControl for Outbox binding checks: %v", err)
	}
	cases := []struct {
		name        string
		messageID   string
		destination string
		availableAt time.Time
		createdAt   time.Time
	}{
		{name: "wrong destination", messageID: "outbox-safety-wrong-destination", destination: "untrusted-consumer", availableAt: control.IssuedAt, createdAt: control.IssuedAt},
		{name: "delayed availability", messageID: "outbox-safety-delayed", destination: "agent-runtime-control", availableAt: control.IssuedAt.Add(time.Second), createdAt: control.IssuedAt},
		{name: "shifted creation", messageID: "outbox-safety-shifted", destination: "agent-runtime-control", availableAt: control.IssuedAt.Add(time.Second), createdAt: control.IssuedAt.Add(time.Second)},
	}
	for _, check := range cases {
		message, err := messaging.NewOutboundMessage(
			check.messageID, check.destination, payload, check.availableAt, check.createdAt,
		)
		if err != nil {
			t.Fatalf("construct %s safety Outbox probe: %v", check.name, err)
		}
		if _, err := repository.AppendSystemSafetyControl(ctx, tenantID, control, message); !errors.Is(err, messaging.ErrOutboxConflict) {
			t.Fatalf("SystemSafetyControl %s Outbox = %v, want conflict", check.name, err)
		}
	}
}

func seedSystemSafetyAuthorities(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	control safety.SystemSafetyControl,
	baseTime time.Time,
) {
	t.Helper()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin trusted safety authority seed: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `
		INSERT INTO agent.platform_safety_controllers (
		    tenant_id, issuer_subject_id, admitted_at, admission_digest
		) VALUES ($1, $2, $3, $4)
	`, string(tenantID), control.IssuerSubjectID, baseTime.Add(19*time.Minute), digestWith("5")); err != nil {
		t.Fatalf("seed trusted Safety Controller authority: %v", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO agent.safety_trigger_evidence (
		    tenant_id, work_order_id, evidence_contract_id, evidence_id,
		    evidence_digest, action, reason, observed_at, admitted_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	`, string(tenantID), control.WorkOrderID, control.EvidenceContractID, control.EvidenceID,
		control.EvidenceDigest, string(control.Action), string(control.Reason), control.ObservedAt,
		baseTime.Add(21*time.Minute)); err != nil {
		t.Fatalf("seed trusted safety trigger evidence: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit trusted safety authority seed: %v", err)
	}
}

func assertDatabaseRejectsInvalidControlFacts(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) {
	t.Helper()
	checks := []struct {
		name     string
		query    string
		sqlState string
	}{
		{
			name: "policy revocation pause evidence",
			query: `INSERT INTO agent.safety_trigger_evidence (
			            tenant_id, work_order_id, evidence_contract_id, evidence_id,
			            evidence_digest, action, reason, observed_at, admitted_at
			        ) VALUES (
			            'tenant-a', 'work-user', 'urn:agent-platform:policy-revocation:v1',
			            'evidence-policy-pause',
			            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
			            'pause', 'policy_revoked',
			            '2026-07-27T00:00:00Z', '2026-07-27T00:01:00Z'
			        )`,
			sqlState: "23514",
		},
		{
			name: "system resume",
			query: `UPDATE agent.system_safety_controls
			        SET action = 'resume'
			        WHERE safety_control_id = 'safety-system'`,
			sqlState: "23514",
		},
		{
			name: "mixed user and system command authority",
			query: `UPDATE agent.agent_runtime_commands
			        SET system_safety_control_id = 'safety-system',
			            system_safety_control_digest = (
			                SELECT control_digest
			                FROM agent.system_safety_controls
			                WHERE safety_control_id = 'safety-system'
			            )
			        WHERE command_id = 'command-cancel-root'`,
			sqlState: "23514",
		},
		{
			name: "duplicate runtime command sequence",
			query: `UPDATE agent.agent_runtime_commands
			        SET command_sequence = 2
			        WHERE command_id = 'command-user-input'`,
			sqlState: "23505",
		},
		{
			name: "short runtime command idempotency key",
			query: `UPDATE agent.agent_runtime_commands
			        SET idempotency_key = 'short'
			        WHERE command_id = 'command-user-input'`,
			sqlState: "23514",
		},
		{
			name: "empty optional runtime command reason",
			query: `UPDATE agent.agent_runtime_commands
			        SET reason = ''
			        WHERE command_id = 'command-user-input'`,
			sqlState: "23514",
		},
	}
	for _, check := range checks {
		_, err := pool.Exec(ctx, check.query)
		var databaseError *pgconn.PgError
		if !errors.As(err, &databaseError) || databaseError.Code != check.sqlState {
			t.Fatalf("database %s rejection = %v, want SQLSTATE %s", check.name, err, check.sqlState)
		}
	}
}

func persistenceRunSQL(ctx context.Context, pool *pgxpool.Pool, tenantID tenancy.TenantID, statement string) error {
	return persistenceRunSQLArgs(ctx, pool, tenantID, statement)
}

func rescheduleOutboxForRetry(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	messageID string,
	nextAttemptAt time.Time,
) {
	t.Helper()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin control Outbox retry schedule: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", string(tenantID)); err != nil {
		t.Fatalf("set control Outbox retry TenantContext: %v", err)
	}
	result, err := tx.Exec(ctx, `
		UPDATE agent.outbox_messages
		SET next_attempt_at = $1, updated_at = $1
		WHERE message_id = $2
	`, nextAttemptAt, messageID)
	if err != nil {
		t.Fatalf("reschedule control Outbox retry: %v", err)
	}
	if result.RowsAffected() != 1 {
		t.Fatalf("rescheduled control Outbox rows = %d, want 1", result.RowsAffected())
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit control Outbox retry schedule: %v", err)
	}
}

func persistenceRunSQLArgs(
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	statement string,
	arguments ...any,
) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", string(tenantID)); err != nil {
		return err
	}
	_, err = tx.Exec(ctx, statement, arguments...)
	return err
}

func makeRuntimeCommand(t *testing.T, command safety.RuntimeCommand) safety.RuntimeCommand {
	t.Helper()
	digest, err := command.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute runtime command digest: %v", err)
	}
	command.CommandDigest = digest
	if err := command.Validate(); err != nil {
		t.Fatalf("validate runtime command: %v", err)
	}
	return command
}

func mustSafetyDigest(t *testing.T, control safety.SystemSafetyControl) string {
	t.Helper()
	digest, err := control.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute safety control digest: %v", err)
	}
	return digest
}

func mustFanoutDigest(t *testing.T, snapshot safety.FanoutSnapshot) string {
	t.Helper()
	digest, err := snapshot.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute fanout digest: %v", err)
	}
	return digest
}

func mustCommandOutbox(t *testing.T, messageID string, command safety.RuntimeCommand) messaging.OutboundMessage {
	t.Helper()
	payload, err := command.Payload()
	if err != nil {
		t.Fatalf("encode runtime command: %v", err)
	}
	return mustControlOutbox(t, messageID, payload, command.CreatedAt)
}

func controlOutboxPointer(
	t *testing.T,
	messageID string,
	control safety.SystemSafetyControl,
) *messaging.OutboundMessage {
	t.Helper()
	payload, err := control.Payload()
	if err != nil {
		t.Fatalf("encode safety control: %v", err)
	}
	message := mustControlOutbox(t, messageID, payload, control.IssuedAt)
	return &message
}

func mustControlOutbox(
	t *testing.T,
	messageID string,
	payload []byte,
	createdAt time.Time,
) messaging.OutboundMessage {
	t.Helper()
	message, err := messaging.NewOutboundMessage(
		messageID, "agent-runtime-control", payload, createdAt, createdAt,
	)
	if err != nil {
		t.Fatalf("create control Outbox message: %v", err)
	}
	return message
}

func digestWith(nibble string) string {
	return "sha256:" + nibble + strings.Repeat("0", 63)
}
