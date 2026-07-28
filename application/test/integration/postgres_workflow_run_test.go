//go:build integration

package integration_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	domain "github.com/shell-echo/agent/internal/domain/orchestration"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/persistence"
	"github.com/shell-echo/agent/internal/safety"
)

const insertWorkflowRunSQL = `
	INSERT INTO agent.workflow_runs (
		tenant_id, workflow_run_id, work_order_id,
		workflow_id, workflow_version, workflow_definition_build_id,
		workflow_definition_digest, orchestration_engine_id,
		orchestration_engine_version, workflow_execution_id,
		native_execution_reference_digest, worker_deployment, worker_build_id,
		versioning_behavior, orchestration_binding_digest, created_at
	) VALUES (
		$1, $2, $3, $4, $5, $6, $7, $8,
		$9, $10, $11, $12, $13, $14, $15, $16
	)
`

func TestPostgreSQLWorkflowRunLedger(t *testing.T) {
	ctx := context.Background()
	adminDSN := requiredEnv(t, "AGENT_TEST_ADMIN_DSN")
	adminPool := openPool(t, adminDSN, 4)
	createDatabase(t, ctx, adminPool, agentDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, agentDatabase) })

	databaseAdminDSN := replaceDatabase(t, adminDSN, agentDatabase, "postgres", "b021-integration-admin")
	runGoose(t, databaseAdminDSN, "up", true)
	assertMigrationVersion(t, databaseAdminDSN, 4)
	databaseAdminPool := openPool(t, databaseAdminDSN, 4)
	assertSecuredTables(t, ctx, databaseAdminPool, []string{"workflow_runs"})
	assertExactApplicationPrivileges(t, ctx, databaseAdminPool)
	createApplicationLogin(t, ctx, databaseAdminPool)

	applicationDSN := replaceDatabase(t, adminDSN, agentDatabase, applicationLogin, applicationPass)
	applicationPool := openPool(t, applicationDSN, 16)
	runner, err := persistence.NewTransactionRunner(applicationPool)
	if err != nil {
		t.Fatalf("create transaction runner: %v", err)
	}
	clients, err := persistence.NewClientApplicationRepository(runner)
	if err != nil {
		t.Fatalf("create ClientApplication repository: %v", err)
	}
	workOrders, err := persistence.NewRuntimeControlRepository(runner)
	if err != nil {
		t.Fatalf("create WorkOrder authority repository: %v", err)
	}
	workflowRuns, err := persistence.NewWorkflowRunRepository(runner)
	if err != nil {
		t.Fatalf("create WorkflowRun repository: %v", err)
	}

	baseTime := time.Date(2026, time.July, 28, 1, 0, 0, 0, time.UTC)
	tenantA := tenancy.Tenant{ID: "tenant-a", DisplayName: "Tenant A", CreatedAt: baseTime}
	tenantB := tenancy.Tenant{ID: "tenant-b", DisplayName: "Tenant B", CreatedAt: baseTime}
	registerClient(t, ctx, clients, tenantA, "client-a", baseTime)
	registerClient(t, ctx, clients, tenantB, "client-b", baseTime)
	admitWorkflowRunWorkOrders(t, ctx, workOrders, tenantA.ID, baseTime, []string{
		"work-base", "work-conflict", "work-concurrent", "work-rollback", "work-direct",
	})
	admitWorkflowRunWorkOrders(t, ctx, workOrders, tenantB.ID, baseTime, []string{
		"work-b-global-id", "work-b-binding",
	})

	base := newWorkflowRun(t, tenantA.ID, "workflow-run-base", "work-base", "native-base", baseTime.Add(time.Minute))
	if outcome, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantA.ID, base); err != nil || outcome != domain.ConfirmInserted {
		t.Fatalf("confirm WorkflowRun = %s, %v", outcome, err)
	}
	if outcome, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantA.ID, base); err != nil || outcome != domain.ConfirmReplay {
		t.Fatalf("replay WorkflowRun = %s, %v", outcome, err)
	}
	persisted, err := workflowRuns.Get(ctx, tenantA.ID, base.WorkflowRunID)
	if err != nil || !persisted.Matches(base) {
		t.Fatalf("read WorkflowRun = %#v, %v", persisted, err)
	}
	if _, err := workflowRuns.Get(ctx, tenantB.ID, base.WorkflowRunID); !errors.Is(err, domain.ErrWorkflowRunNotFound) {
		t.Fatalf("cross-Tenant WorkflowRun read = %v, want not found", err)
	}
	if _, err := workflowRuns.Get(ctx, "", base.WorkflowRunID); !errors.Is(err, tenancy.ErrMissingTenantContext) {
		t.Fatalf("missing Tenant WorkflowRun read = %v, want missing Tenant context", err)
	}
	if _, err := workflowRuns.Get(ctx, tenantA.ID, strings.Repeat("x", 201)); !errors.Is(err, domain.ErrInvalidWorkflowRun) {
		t.Fatalf("oversized WorkflowRun ID read = %v, want invalid WorkflowRun", err)
	}

	changed := base
	changed.OrchestrationBinding.NativeExecutionReferenceDigest = testSHA256("native-changed")
	changed.OrchestrationBinding.BindingDigest = mustBindingDigest(t, changed.OrchestrationBinding)
	if _, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantA.ID, changed); !errors.Is(err, domain.ErrWorkflowRunConflict) {
		t.Fatalf("same ID with changed binding = %v, want WorkflowRun conflict", err)
	}
	workOrderConflict := newWorkflowRun(
		t, tenantA.ID, "workflow-run-work-order-conflict", base.WorkOrderID,
		"native-work-order-conflict", baseTime.Add(2*time.Minute),
	)
	if _, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantA.ID, workOrderConflict); !errors.Is(err, domain.ErrWorkflowRunConflict) {
		t.Fatalf("second WorkflowRun for one WorkOrder = %v, want conflict", err)
	}
	crossTenantID := newWorkflowRun(
		t, tenantB.ID, base.WorkflowRunID, "work-b-global-id",
		"native-tenant-b", baseTime.Add(2*time.Minute),
	)
	if _, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantB.ID, crossTenantID); !errors.Is(err, domain.ErrWorkflowRunConflict) {
		t.Fatalf("cross-Tenant WorkflowRun ID reuse = %v, want conflict", err)
	}
	crossTenantBinding := newWorkflowRun(
		t, tenantB.ID, "workflow-run-b-binding", "work-b-binding",
		"unused", baseTime.Add(2*time.Minute),
	)
	crossTenantBinding.OrchestrationBinding = base.OrchestrationBinding
	if _, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantB.ID, crossTenantBinding); !errors.Is(err, domain.ErrWorkflowRunConflict) {
		t.Fatalf("cross-Tenant orchestration binding reuse = %v, want conflict", err)
	}
	if _, err := workflowRuns.ConfirmWorkflowStart(ctx, tenantB.ID, base); !errors.Is(err, domain.ErrStartAuthority) {
		t.Fatalf("cross-Tenant start authority = %v, want invalid authority", err)
	}

	assertWorkflowRunAppendOnly(t, ctx, applicationPool, tenantA.ID, base.WorkflowRunID)
	assertWorkflowRunDirectConstraints(t, ctx, applicationPool, tenantA.ID, tenantB.ID, baseTime)
	assertWorkflowRunRollback(t, ctx, applicationPool, workflowRuns, tenantA.ID, baseTime)
	assertConcurrentWorkflowRunConfirmation(t, ctx, workflowRuns, tenantA.ID, baseTime)
	assertPoolTenantContextEmpty(t, ctx, applicationPool)

	downOutput := runGoose(t, databaseAdminDSN, "down", false)
	if !strings.Contains(downOutput, "contains authoritative data and is forward-only") {
		t.Fatalf("data-bearing WorkflowRun Down was not classified forward-only: %s", downOutput)
	}
	assertMigrationVersion(t, databaseAdminDSN, 4)
}

func admitWorkflowRunWorkOrders(
	t *testing.T,
	ctx context.Context,
	repository *persistence.RuntimeControlRepository,
	tenantID tenancy.TenantID,
	createdAt time.Time,
	workOrderIDs []string,
) {
	t.Helper()
	authorities := make([]safety.WorkOrderAuthority, 0, len(workOrderIDs))
	for _, workOrderID := range workOrderIDs {
		authorities = append(authorities, safety.WorkOrderAuthority{
			TenantID: tenantID, WorkOrderID: workOrderID,
			State: safety.WorkOrderAccepted, ActiveWorkVersion: 1,
			ChildAdmissionOpen: true, CreatedAt: createdAt,
		})
	}
	if err := repository.AdmitAuthorities(ctx, tenantID, persistence.RuntimeControlAuthorities{
		WorkOrders: authorities,
	}); err != nil {
		t.Fatalf("admit WorkflowRun WorkOrders for %s: %v", tenantID, err)
	}
}

func newWorkflowRun(
	t *testing.T,
	tenantID tenancy.TenantID,
	workflowRunID string,
	workOrderID string,
	nativeIdentity string,
	createdAt time.Time,
) domain.WorkflowRun {
	t.Helper()
	binding := domain.OrchestrationBinding{
		EngineID: "temporal", EngineVersion: "1.29.7",
		WorkflowExecutionID:            "workflow-execution/" + workflowRunID,
		NativeExecutionReferenceDigest: testSHA256(nativeIdentity),
		WorkerDeployment:               "agent-worker-b031", WorkerBuildID: "b03.1-test",
		VersioningBehavior: domain.VersioningPinned,
	}
	binding.BindingDigest = mustBindingDigest(t, binding)
	return domain.WorkflowRun{
		WorkflowRunID: workflowRunID, TenantID: tenantID, WorkOrderID: workOrderID,
		Workflow: domain.WorkflowDefinition{
			ID: "workflow.agent-execution", Version: "1.0.0",
			DefinitionBuildID: "b03.1-test", DefinitionDigest: testSHA256("workflow-definition"),
		},
		OrchestrationBinding: binding,
		CreatedAt:            createdAt,
	}
}

func mustBindingDigest(t *testing.T, binding domain.OrchestrationBinding) string {
	t.Helper()
	digest, err := binding.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute orchestration binding digest: %v", err)
	}
	return digest
}

func testSHA256(value string) string {
	digest := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(digest[:])
}

func assertWorkflowRunAppendOnly(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	workflowRunID string,
) {
	t.Helper()
	if _, err := pool.Exec(ctx, `
		UPDATE agent.workflow_runs
		SET worker_build_id = 'forbidden'
		WHERE tenant_id = $1 AND workflow_run_id = $2
	`, tenantID, workflowRunID); err == nil {
		t.Fatal("Application role updated an immutable WorkflowRun")
	}
	if _, err := pool.Exec(ctx, `
		DELETE FROM agent.workflow_runs
		WHERE tenant_id = $1 AND workflow_run_id = $2
	`, tenantID, workflowRunID); err == nil {
		t.Fatal("Application role deleted an immutable WorkflowRun")
	}
}

func assertWorkflowRunDirectConstraints(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	tenantA tenancy.TenantID,
	tenantB tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	valid := newWorkflowRun(t, tenantA, "workflow-run-direct", "work-direct", "native-direct", baseTime.Add(time.Minute))
	tests := []struct {
		name     string
		mutate   func([]any)
		tenantID tenancy.TenantID
	}{
		{"blank identity", func(args []any) { args[1] = "" }, tenantA},
		{"malformed definition digest", func(args []any) { args[6] = "sha256:invalid" }, tenantA},
		{"unsupported versioning", func(args []any) { args[13] = "unversioned" }, tenantA},
		{"non-finite creation time", func(args []any) { args[15] = "infinity" }, tenantA},
		{"cross-Tenant insert", func(args []any) {
			args[0] = string(tenantB)
			args[2] = "work-b-global-id"
		}, tenantA},
	}
	for _, testCase := range tests {
		t.Run("direct SQL rejects "+testCase.name, func(t *testing.T) {
			args := workflowRunSQLArgs(valid)
			testCase.mutate(args)
			tx, err := pool.Begin(ctx)
			if err != nil {
				t.Fatalf("begin direct SQL constraint transaction: %v", err)
			}
			defer func() { _ = tx.Rollback(ctx) }()
			if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", testCase.tenantID); err != nil {
				t.Fatalf("set direct SQL Tenant context: %v", err)
			}
			if _, err := tx.Exec(ctx, insertWorkflowRunSQL, args...); err == nil {
				t.Fatalf("direct SQL accepted %s", testCase.name)
			}
		})
	}
}

func assertWorkflowRunRollback(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	repository *persistence.WorkflowRunRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	run := newWorkflowRun(t, tenantID, "workflow-run-rollback", "work-rollback", "native-rollback", baseTime.Add(time.Minute))
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin WorkflowRun rollback transaction: %v", err)
	}
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", tenantID); err != nil {
		_ = tx.Rollback(ctx)
		t.Fatalf("set WorkflowRun rollback Tenant context: %v", err)
	}
	if _, err := tx.Exec(ctx, insertWorkflowRunSQL, workflowRunSQLArgs(run)...); err != nil {
		_ = tx.Rollback(ctx)
		t.Fatalf("insert WorkflowRun before rollback: %v", err)
	}
	if err := tx.Rollback(ctx); err != nil {
		t.Fatalf("rollback WorkflowRun transaction: %v", err)
	}
	if _, err := repository.Get(ctx, tenantID, run.WorkflowRunID); !errors.Is(err, domain.ErrWorkflowRunNotFound) {
		t.Fatalf("rolled-back WorkflowRun read = %v, want not found", err)
	}
	if outcome, err := repository.ConfirmWorkflowStart(ctx, tenantID, run); err != nil || outcome != domain.ConfirmInserted {
		t.Fatalf("confirm WorkflowRun after rollback = %s, %v", outcome, err)
	}
	assertPoolTenantContextEmpty(t, ctx, pool)
}

func assertConcurrentWorkflowRunConfirmation(
	t *testing.T,
	ctx context.Context,
	repository *persistence.WorkflowRunRepository,
	tenantID tenancy.TenantID,
	baseTime time.Time,
) {
	t.Helper()
	run := newWorkflowRun(
		t, tenantID, "workflow-run-concurrent", "work-concurrent",
		"native-concurrent", baseTime.Add(time.Minute),
	)
	const contenders = 16
	results := make(chan domain.ConfirmOutcome, contenders)
	errorsFound := make(chan error, contenders)
	var group sync.WaitGroup
	for range contenders {
		group.Add(1)
		go func() {
			defer group.Done()
			outcome, err := repository.ConfirmWorkflowStart(ctx, tenantID, run)
			if err != nil {
				errorsFound <- err
				return
			}
			results <- outcome
		}()
	}
	group.Wait()
	close(results)
	close(errorsFound)
	for err := range errorsFound {
		t.Errorf("concurrent WorkflowRun confirmation: %v", err)
	}
	inserted := 0
	replayed := 0
	for outcome := range results {
		switch outcome {
		case domain.ConfirmInserted:
			inserted++
		case domain.ConfirmReplay:
			replayed++
		default:
			t.Errorf("unexpected concurrent confirmation outcome %q", outcome)
		}
	}
	if inserted != 1 || replayed != contenders-1 {
		t.Fatalf("concurrent confirmation inserted/replayed = %d/%d, want 1/%d", inserted, replayed, contenders-1)
	}
}

func workflowRunSQLArgs(run domain.WorkflowRun) []any {
	return []any{
		string(run.TenantID), run.WorkflowRunID, run.WorkOrderID,
		run.Workflow.ID, run.Workflow.Version, run.Workflow.DefinitionBuildID,
		run.Workflow.DefinitionDigest, run.OrchestrationBinding.EngineID,
		run.OrchestrationBinding.EngineVersion, run.OrchestrationBinding.WorkflowExecutionID,
		run.OrchestrationBinding.NativeExecutionReferenceDigest,
		run.OrchestrationBinding.WorkerDeployment, run.OrchestrationBinding.WorkerBuildID,
		string(run.OrchestrationBinding.VersioningBehavior), run.OrchestrationBinding.BindingDigest,
		run.CreatedAt,
	}
}
