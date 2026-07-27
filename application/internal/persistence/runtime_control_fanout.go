package persistence

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
	"github.com/shell-echo/agent/internal/messaging"
	"github.com/shell-echo/agent/internal/safety"
)

type FanoutDispatchTarget struct {
	Command             safety.RuntimeCommand
	CommandOutbox       messaging.OutboundMessage
	SystemSafetyControl *safety.SystemSafetyControl
	SafetyControlOutbox *messaging.OutboundMessage
}

type FanoutCreation struct {
	Snapshot                  safety.FanoutSnapshot
	ExpectedActiveWorkVersion int64
	Dispatch                  []FanoutDispatchTarget
}

func (repository *RuntimeControlRepository) CreateFanout(
	ctx context.Context,
	tenantID tenancy.TenantID,
	creation FanoutCreation,
) (safety.AppendOutcome, error) {
	if creation.Snapshot.FanoutVersion != 1 || creation.ExpectedActiveWorkVersion < 1 {
		return "", safety.ErrInvalidControl
	}
	if err := creation.Snapshot.Validate(tenantID); err != nil {
		return "", err
	}
	if len(creation.Dispatch) != len(creation.Snapshot.Targets) {
		return "", safety.ErrFanoutCoverageConflict
	}
	if creation.Snapshot.AuthorityKind == safety.FanoutSystemAuthority {
		for _, dispatch := range creation.Dispatch {
			if dispatch.SystemSafetyControl == nil || dispatch.SafetyControlOutbox == nil {
				return "", safety.ErrInvalidControl
			}
			if err := repository.verifySystemSafetyAuthority(ctx, tenantID, *dispatch.SystemSafetyControl); err != nil {
				return "", err
			}
		}
	}

	var outcome safety.AppendOutcome
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		var err error
		outcome, err = createFanout(ctx, txRepository, tenantID, creation)
		return err
	})
	return outcome, err
}

func (repository *RuntimeControlRepository) GetFanoutSnapshot(
	ctx context.Context,
	tenantID tenancy.TenantID,
	fanoutID string,
) (safety.FanoutSnapshot, error) {
	if err := safety.ValidateFanoutID(fanoutID); err != nil {
		return safety.FanoutSnapshot{}, err
	}
	var snapshot safety.FanoutSnapshot
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		root, err := txRepository.queries.LockAgentRunControlFanout(
			ctx,
			agentdb.LockAgentRunControlFanoutParams{TenantID: string(tenantID), FanoutID: fanoutID},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrControlNotFound
		}
		if err != nil {
			return fmt.Errorf("lock fanout for reconciliation: %w", err)
		}
		rows, err := txRepository.queries.ListAgentRunControlFanoutTargets(
			ctx,
			agentdb.ListAgentRunControlFanoutTargetsParams{
				TenantID: string(tenantID), FanoutID: fanoutID,
			},
		)
		if err != nil {
			return fmt.Errorf("lock fanout targets for reconciliation: %w", err)
		}
		version, err := txRepository.queries.GetAgentRunControlFanoutVersion(
			ctx,
			agentdb.GetAgentRunControlFanoutVersionParams{
				TenantID: string(tenantID), FanoutID: fanoutID, FanoutVersion: root.LatestVersion,
			},
		)
		if err != nil {
			return fmt.Errorf("read latest fanout version for reconciliation: %w", err)
		}

		snapshot = fanoutSnapshotFromRows(root, rows, root.UpdatedAt.Time)
		snapshot.FanoutVersion = root.LatestVersion
		snapshot.FanoutDigest = root.LatestDigest
		if version.PreviousFanoutDigest != nil {
			snapshot.PreviousFanoutDigest = *version.PreviousFanoutDigest
		}
		if err := snapshot.Validate(tenantID); err != nil {
			return fmt.Errorf("validate reconciled fanout snapshot: %w", err)
		}
		return nil
	})
	return snapshot, err
}

func (repository *RuntimeControlRepository) ClaimFanoutTargets(
	ctx context.Context,
	tenantID tenancy.TenantID,
	request safety.FanoutClaimRequest,
) ([]safety.ClaimedFanoutTarget, error) {
	if err := request.Validate(); err != nil {
		return nil, err
	}
	var claimed []safety.ClaimedFanoutTarget
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := request.WorkerID
		rows, err := txRepository.queries.ClaimAgentRunControlFanoutTargets(
			ctx,
			agentdb.ClaimAgentRunControlFanoutTargetsParams{
				WorkerID: &workerID, LeaseDuration: databaseInterval(request.LeaseDuration),
				TenantID: string(tenantID), BatchSize: request.BatchSize,
			},
		)
		if err != nil {
			return fmt.Errorf("claim fanout targets: %w", err)
		}
		claimed = make([]safety.ClaimedFanoutTarget, 0, len(rows))
		for _, row := range rows {
			mapped, err := mapClaimedFanoutTarget(row, tenantID, request.WorkerID)
			if err != nil {
				return err
			}
			claimed = append(claimed, mapped)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(claimed, func(i, j int) bool {
		if claimed[i].FanoutID == claimed[j].FanoutID {
			return claimed[i].AgentRunID < claimed[j].AgentRunID
		}
		return claimed[i].FanoutID < claimed[j].FanoutID
	})
	return claimed, nil
}

func (repository *RuntimeControlRepository) RenewFanoutTargetLease(
	ctx context.Context,
	tenantID tenancy.TenantID,
	lease safety.FanoutLease,
	leaseDuration time.Duration,
) error {
	if err := lease.Validate(); err != nil {
		return err
	}
	if err := (safety.FanoutClaimRequest{
		WorkerID: lease.WorkerID, BatchSize: 1, LeaseDuration: leaseDuration,
	}).Validate(); err != nil {
		return err
	}
	return repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workerID := lease.WorkerID
		_, err := txRepository.queries.RenewAgentRunControlFanoutTargetLease(
			ctx,
			agentdb.RenewAgentRunControlFanoutTargetLeaseParams{
				LeaseDuration: databaseInterval(leaseDuration), TenantID: string(tenantID),
				FanoutID: lease.FanoutID, AgentRunID: lease.AgentRunID,
				WorkerID: &workerID, ClaimFencingToken: lease.ClaimFencingToken,
			},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrFanoutLeaseLost
		}
		if err != nil {
			return fmt.Errorf("renew fanout target lease: %w", err)
		}
		return nil
	})
}

func (repository *RuntimeControlRepository) ProgressFanoutTarget(
	ctx context.Context,
	tenantID tenancy.TenantID,
	lease safety.FanoutLease,
	nextState safety.ControlState,
) (safety.FanoutSnapshot, error) {
	if err := lease.Validate(); err != nil {
		return safety.FanoutSnapshot{}, err
	}
	var snapshot safety.FanoutSnapshot
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		root, err := txRepository.queries.LockAgentRunControlFanout(
			ctx,
			agentdb.LockAgentRunControlFanoutParams{TenantID: string(tenantID), FanoutID: lease.FanoutID},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrControlNotFound
		}
		if err != nil {
			return fmt.Errorf("lock fanout: %w", err)
		}
		rows, err := txRepository.queries.ListAgentRunControlFanoutTargets(
			ctx,
			agentdb.ListAgentRunControlFanoutTargetsParams{
				TenantID: string(tenantID), FanoutID: lease.FanoutID,
			},
		)
		if err != nil {
			return fmt.Errorf("lock fanout targets: %w", err)
		}
		var current *agentdb.AgentRunControlFanoutTarget
		for index := range rows {
			if rows[index].AgentRunID == lease.AgentRunID {
				current = &rows[index]
				break
			}
		}
		if current == nil || current.ClaimWorkerID == nil || *current.ClaimWorkerID != lease.WorkerID ||
			current.ClaimFencingToken != lease.ClaimFencingToken {
			return safety.ErrFanoutLeaseLost
		}
		from := safety.ControlState(current.ControlState)
		if from == nextState || !safety.CanProgress(from, nextState) {
			return safety.ErrFanoutStateRegression
		}
		workerID := lease.WorkerID
		previousUpdatedAt := current.UpdatedAt.Time
		if root.UpdatedAt.Time.After(previousUpdatedAt) {
			previousUpdatedAt = root.UpdatedAt.Time
		}
		progressed, err := txRepository.queries.ProgressAgentRunControlFanoutTarget(
			ctx,
			agentdb.ProgressAgentRunControlFanoutTargetParams{
				PreviousUpdatedAt: timestamp(previousUpdatedAt), ControlState: string(nextState),
				TenantID: string(tenantID), FanoutID: lease.FanoutID,
				AgentRunID: lease.AgentRunID, ExpectedControlState: current.ControlState,
				WorkerID: &workerID, ClaimFencingToken: lease.ClaimFencingToken,
			},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrFanoutLeaseLost
		}
		if err != nil {
			return fmt.Errorf("progress fanout target: %w", err)
		}
		for index := range rows {
			if rows[index].AgentRunID == progressed.AgentRunID {
				rows[index] = progressed
				break
			}
		}

		snapshot = fanoutSnapshotFromRows(root, rows, progressed.UpdatedAt.Time)
		snapshot.FanoutVersion = root.LatestVersion + 1
		snapshot.PreviousFanoutDigest = root.LatestDigest
		digest, err := snapshot.ExpectedDigest()
		if err != nil {
			return err
		}
		snapshot.FanoutDigest = digest
		if err := snapshot.Validate(tenantID); err != nil {
			return err
		}
		if err := insertFanoutVersion(ctx, txRepository, snapshot); err != nil {
			return err
		}
		_, err = txRepository.queries.AdvanceAgentRunControlFanoutVersion(
			ctx,
			agentdb.AdvanceAgentRunControlFanoutVersionParams{
				NextVersion: snapshot.FanoutVersion, NextDigest: snapshot.FanoutDigest,
				UpdatedAt: timestamp(snapshot.UpdatedAt), TenantID: string(tenantID),
				FanoutID: snapshot.FanoutID, PreviousDigest: snapshot.PreviousFanoutDigest,
			},
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return safety.ErrFanoutStateRegression
		}
		if err != nil {
			return fmt.Errorf("advance fanout version cursor: %w", err)
		}
		return nil
	})
	return snapshot, err
}

func createFanout(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	creation FanoutCreation,
) (safety.AppendOutcome, error) {
	snapshot := creation.Snapshot
	workOrder, err := repository.queries.LockWorkOrder(ctx, agentdb.LockWorkOrderParams{
		TenantID: string(tenantID), WorkOrderID: snapshot.WorkOrderID,
	})
	if err != nil {
		return "", classifyAuthorityRead("lock fanout WorkOrder", err)
	}
	existing, err := repository.queries.GetAgentRunControlFanout(ctx, agentdb.GetAgentRunControlFanoutParams{
		TenantID: string(tenantID), FanoutID: snapshot.FanoutID,
	})
	if err == nil {
		if err := verifyFanoutReplay(ctx, repository, tenantID, existing, creation); err != nil {
			return "", err
		}
		return safety.AppendReplay, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return "", fmt.Errorf("read fanout identity: %w", err)
	}
	if isTerminalWorkOrderState(workOrder.State) {
		return "", safety.ErrInvalidAuthority
	}

	controlRequestID := (*string)(nil)
	evidenceContractID := (*string)(nil)
	evidenceID := (*string)(nil)
	if snapshot.AuthorityKind == safety.FanoutUserAuthority {
		controlRequestID = optional(snapshot.AuthorityID)
	} else {
		evidenceContractID = optional(snapshot.SafetyEvidenceContractID)
		evidenceID = optional(snapshot.AuthorityID)
	}
	_, err = repository.queries.InsertAgentRunControlFanout(ctx, agentdb.InsertAgentRunControlFanoutParams{
		TenantID: string(tenantID), WorkOrderID: snapshot.WorkOrderID,
		FanoutID: snapshot.FanoutID, Action: string(snapshot.Action),
		AuthorityKind: string(snapshot.AuthorityKind), AuthorityID: snapshot.AuthorityID,
		AuthorityDigest:           snapshot.AuthorityDigest,
		ExpectedActiveWorkVersion: creation.ExpectedActiveWorkVersion,
		ControlRequestID:          controlRequestID,
		SafetyEvidenceContractID:  evidenceContractID, SafetyEvidenceID: evidenceID,
		FanoutDigest: snapshot.FanoutDigest, CreatedAt: timestamp(snapshot.CreatedAt),
	})
	if errors.Is(err, pgx.ErrNoRows) {
		return "", safety.ErrAuthorityConflict
	}
	if err != nil {
		return "", classifyControlWrite("insert AgentRunControlFanout", err)
	}
	if _, err := repository.queries.CloseWorkOrderChildAdmission(
		ctx,
		agentdb.CloseWorkOrderChildAdmissionParams{
			UpdatedAt: timestamp(snapshot.CreatedAt), TenantID: string(tenantID),
			WorkOrderID:               snapshot.WorkOrderID,
			ExpectedActiveWorkVersion: creation.ExpectedActiveWorkVersion,
		},
	); errors.Is(err, pgx.ErrNoRows) {
		return "", safety.ErrAuthorityConflict
	} else if err != nil {
		return "", fmt.Errorf("close WorkOrder child admission: %w", err)
	}

	activeAgentRuns, err := repository.queries.ListActiveAgentRunsForFanout(
		ctx,
		agentdb.ListActiveAgentRunsForFanoutParams{
			TenantID: string(tenantID), WorkOrderID: snapshot.WorkOrderID,
		},
	)
	if err != nil {
		return "", fmt.Errorf("lock active AgentRun set: %w", err)
	}
	activeTargets, err := repository.queries.ListActiveRuntimeTargetsForFanout(
		ctx,
		agentdb.ListActiveRuntimeTargetsForFanoutParams{
			TenantID: string(tenantID), WorkOrderID: snapshot.WorkOrderID,
		},
	)
	if err != nil {
		return "", fmt.Errorf("lock active fanout target set: %w", err)
	}
	if err := validateFanoutCoverage(snapshot, creation.Dispatch, activeAgentRuns, activeTargets); err != nil {
		return "", err
	}
	dispatchByCommand := make(map[string]FanoutDispatchTarget, len(creation.Dispatch))
	for _, dispatch := range creation.Dispatch {
		dispatchByCommand[dispatch.Command.CommandID] = dispatch
	}
	for _, target := range snapshot.Targets {
		dispatch := dispatchByCommand[target.CommandID]
		if snapshot.AuthorityKind == safety.FanoutSystemAuthority {
			if dispatch.SystemSafetyControl == nil || dispatch.SafetyControlOutbox == nil {
				return "", safety.ErrInvalidControl
			}
			control := *dispatch.SystemSafetyControl
			if control.SafetyControlID != target.SystemSafetyControlID ||
				control.ControlDigest != target.SystemSafetyControlDigest ||
				control.RuntimeRunID != target.RuntimeRunID || control.WorkOrderID != snapshot.WorkOrderID ||
				control.Action != snapshot.Action || control.EvidenceContractID != snapshot.SafetyEvidenceContractID ||
				control.EvidenceID != snapshot.AuthorityID || control.EvidenceDigest != snapshot.AuthorityDigest {
				return "", safety.ErrInvalidAuthority
			}
			outcome, err := appendSystemSafetyControl(
				ctx, repository, tenantID, control, *dispatch.SafetyControlOutbox,
			)
			if err != nil {
				return "", err
			}
			if outcome != safety.AppendInserted {
				return "", safety.ErrDigestConflict
			}
		} else if dispatch.SystemSafetyControl != nil || dispatch.SafetyControlOutbox != nil {
			return "", safety.ErrInvalidControl
		}
		outcome, err := appendRuntimeCommand(
			ctx, repository, tenantID, dispatch.Command, dispatch.CommandOutbox,
		)
		if err != nil {
			return "", err
		}
		if outcome != safety.AppendInserted {
			return "", safety.ErrDigestConflict
		}
		if _, err := repository.queries.InsertAgentRunControlFanoutTarget(
			ctx,
			agentdb.InsertAgentRunControlFanoutTargetParams{
				TenantID: string(tenantID), WorkOrderID: snapshot.WorkOrderID,
				FanoutID: snapshot.FanoutID, AuthorityKind: string(snapshot.AuthorityKind),
				AgentRunID: target.AgentRunID, RuntimeRunID: target.RuntimeRunID,
				TargetFencingToken:        target.TargetFencingToken,
				SystemSafetyControlID:     optional(target.SystemSafetyControlID),
				SystemSafetyControlDigest: optional(target.SystemSafetyControlDigest),
				CommandID:                 target.CommandID, ControlState: string(target.ControlState),
				UpdatedAt: timestamp(snapshot.UpdatedAt),
			},
		); err != nil {
			return "", classifyControlWrite("insert fanout target", err)
		}
	}
	if err := insertFanoutVersion(ctx, repository, snapshot); err != nil {
		return "", err
	}
	return safety.AppendInserted, nil
}

func verifyFanoutReplay(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	existing agentdb.AgentRunControlFanout,
	creation FanoutCreation,
) error {
	snapshot := creation.Snapshot
	if existing.WorkOrderID != snapshot.WorkOrderID || existing.Action != string(snapshot.Action) ||
		existing.AuthorityKind != string(snapshot.AuthorityKind) || existing.AuthorityID != snapshot.AuthorityID ||
		existing.AuthorityDigest != snapshot.AuthorityDigest ||
		existing.ExpectedActiveWorkVersion != creation.ExpectedActiveWorkVersion ||
		!equalOptional(existing.SafetyEvidenceContractID, snapshot.SafetyEvidenceContractID) {
		return safety.ErrDigestConflict
	}
	version, err := repository.queries.GetAgentRunControlFanoutVersion(
		ctx,
		agentdb.GetAgentRunControlFanoutVersionParams{
			TenantID: string(tenantID), FanoutID: snapshot.FanoutID, FanoutVersion: 1,
		},
	)
	if err != nil {
		return fmt.Errorf("read fanout version-one identity: %w", err)
	}
	if version.FanoutDigest != snapshot.FanoutDigest || version.WorkOrderID != snapshot.WorkOrderID ||
		version.Action != string(snapshot.Action) || version.AuthorityKind != string(snapshot.AuthorityKind) ||
		version.AuthorityID != snapshot.AuthorityID || version.AuthorityDigest != snapshot.AuthorityDigest {
		return safety.ErrDigestConflict
	}
	rows, err := repository.queries.ListAgentRunControlFanoutVersionTargets(
		ctx,
		agentdb.ListAgentRunControlFanoutVersionTargetsParams{
			TenantID: string(tenantID), FanoutID: snapshot.FanoutID, FanoutVersion: 1,
		},
	)
	if err != nil {
		return fmt.Errorf("read fanout version-one targets: %w", err)
	}
	if len(rows) != len(snapshot.Targets) || len(creation.Dispatch) != len(snapshot.Targets) {
		return safety.ErrDigestConflict
	}
	rowsByAgent := make(map[string]agentdb.ListAgentRunControlFanoutVersionTargetsRow, len(rows))
	for _, row := range rows {
		rowsByAgent[row.AgentRunID] = row
	}
	dispatchByCommand := make(map[string]FanoutDispatchTarget, len(creation.Dispatch))
	for _, dispatch := range creation.Dispatch {
		if _, exists := dispatchByCommand[dispatch.Command.CommandID]; exists {
			return safety.ErrDigestConflict
		}
		dispatchByCommand[dispatch.Command.CommandID] = dispatch
	}
	for _, target := range snapshot.Targets {
		row, hasRow := rowsByAgent[target.AgentRunID]
		dispatch, hasDispatch := dispatchByCommand[target.CommandID]
		if !hasRow || !hasDispatch || row.RuntimeRunID != target.RuntimeRunID ||
			row.TargetFencingToken != target.TargetFencingToken || row.CommandID != target.CommandID ||
			row.ControlState != string(target.ControlState) ||
			!equalOptional(row.SystemSafetyControlID, target.SystemSafetyControlID) ||
			!equalOptional(row.SystemSafetyControlDigest, target.SystemSafetyControlDigest) {
			return safety.ErrDigestConflict
		}
		if err := verifyFanoutDispatchReplay(ctx, repository, tenantID, snapshot, target, dispatch); err != nil {
			return err
		}
	}
	return nil
}

func verifyFanoutDispatchReplay(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	snapshot safety.FanoutSnapshot,
	target safety.FanoutTarget,
	dispatch FanoutDispatchTarget,
) error {
	command := dispatch.Command
	if err := command.Validate(); err != nil {
		return err
	}
	if err := validateRuntimeCommandOutbox(command, dispatch.CommandOutbox); err != nil {
		return err
	}
	if command.CommandID != target.CommandID || command.WorkOrderID != snapshot.WorkOrderID ||
		command.RuntimeRunID != target.RuntimeRunID || command.FencingToken != target.TargetFencingToken ||
		command.Type != snapshot.Action {
		return safety.ErrDigestConflict
	}
	commandRow, err := repository.queries.GetAgentRuntimeCommand(
		ctx,
		agentdb.GetAgentRuntimeCommandParams{TenantID: string(tenantID), CommandID: command.CommandID},
	)
	if err != nil {
		return fmt.Errorf("read replayed fanout command: %w", err)
	}
	if commandRow.CommandDigest != command.CommandDigest {
		return safety.ErrDigestConflict
	}
	if commandRow.OutboxMessageID != dispatch.CommandOutbox.MessageID ||
		commandRow.OutboxPayloadDigest != dispatch.CommandOutbox.PayloadDigest {
		return messaging.ErrOutboxConflict
	}
	if _, err := repository.EnqueueOutboxMessage(ctx, dispatch.CommandOutbox); err != nil {
		return err
	}

	if snapshot.AuthorityKind == safety.FanoutUserAuthority {
		if command.AuthorizedControlRequestID != snapshot.AuthorityID || command.SystemSafetyControlID != "" ||
			dispatch.SystemSafetyControl != nil || dispatch.SafetyControlOutbox != nil {
			return safety.ErrDigestConflict
		}
		return nil
	}
	if dispatch.SystemSafetyControl == nil || dispatch.SafetyControlOutbox == nil {
		return safety.ErrDigestConflict
	}
	control := *dispatch.SystemSafetyControl
	if err := control.Validate(tenantID); err != nil {
		return err
	}
	if err := validateSafetyControlOutbox(control, *dispatch.SafetyControlOutbox); err != nil {
		return err
	}
	if command.AuthorizedControlRequestID != "" ||
		command.SystemSafetyControlID != target.SystemSafetyControlID ||
		command.SystemSafetyControlDigest != target.SystemSafetyControlDigest ||
		control.SafetyControlID != target.SystemSafetyControlID ||
		control.ControlDigest != target.SystemSafetyControlDigest ||
		control.RuntimeRunID != target.RuntimeRunID || control.WorkOrderID != snapshot.WorkOrderID ||
		control.Action != snapshot.Action || control.EvidenceContractID != snapshot.SafetyEvidenceContractID ||
		control.EvidenceID != snapshot.AuthorityID || control.EvidenceDigest != snapshot.AuthorityDigest {
		return safety.ErrDigestConflict
	}
	controlRow, err := repository.queries.GetSystemSafetyControl(
		ctx,
		agentdb.GetSystemSafetyControlParams{
			TenantID: string(tenantID), SafetyControlID: control.SafetyControlID,
		},
	)
	if err != nil {
		return fmt.Errorf("read replayed fanout safety control: %w", err)
	}
	if controlRow.ControlDigest != control.ControlDigest {
		return safety.ErrDigestConflict
	}
	if controlRow.OutboxMessageID != dispatch.SafetyControlOutbox.MessageID ||
		controlRow.OutboxPayloadDigest != dispatch.SafetyControlOutbox.PayloadDigest {
		return messaging.ErrOutboxConflict
	}
	_, err = repository.EnqueueOutboxMessage(ctx, *dispatch.SafetyControlOutbox)
	return err
}

func validateFanoutCoverage(
	snapshot safety.FanoutSnapshot,
	dispatch []FanoutDispatchTarget,
	activeAgentRuns []string,
	active []agentdb.ListActiveRuntimeTargetsForFanoutRow,
) error {
	if len(snapshot.Targets) != len(active) || len(dispatch) != len(active) ||
		len(activeAgentRuns) != len(active) {
		return safety.ErrFanoutCoverageConflict
	}
	activeAgentIDs := make(map[string]struct{}, len(activeAgentRuns))
	for _, agentRunID := range activeAgentRuns {
		activeAgentIDs[agentRunID] = struct{}{}
	}
	activeByAgent := make(map[string]agentdb.ListActiveRuntimeTargetsForFanoutRow, len(active))
	for _, target := range active {
		if _, exists := activeAgentIDs[target.AgentRunID]; !exists {
			return safety.ErrFanoutCoverageConflict
		}
		activeByAgent[target.AgentRunID] = target
	}
	dispatchByCommand := make(map[string]FanoutDispatchTarget, len(dispatch))
	for _, value := range dispatch {
		if _, exists := dispatchByCommand[value.Command.CommandID]; exists {
			return safety.ErrFanoutCoverageConflict
		}
		dispatchByCommand[value.Command.CommandID] = value
	}
	for _, target := range snapshot.Targets {
		activeTarget, exists := activeByAgent[target.AgentRunID]
		dispatchTarget, hasDispatch := dispatchByCommand[target.CommandID]
		if !exists || !hasDispatch || activeTarget.RuntimeRunID != target.RuntimeRunID ||
			target.TargetFencingToken != activeTarget.CurrentFencingToken+1 ||
			target.ControlState != safety.ControlPending {
			return safety.ErrFanoutCoverageConflict
		}
		command := dispatchTarget.Command
		if command.CommandID != target.CommandID || command.WorkOrderID != snapshot.WorkOrderID ||
			command.RuntimeRunID != target.RuntimeRunID || command.FencingToken != target.TargetFencingToken ||
			command.Type != snapshot.Action {
			return safety.ErrFanoutCoverageConflict
		}
		if snapshot.AuthorityKind == safety.FanoutUserAuthority {
			if command.AuthorizedControlRequestID != snapshot.AuthorityID || command.SystemSafetyControlID != "" {
				return safety.ErrInvalidAuthority
			}
		} else if command.SystemSafetyControlID != target.SystemSafetyControlID ||
			command.SystemSafetyControlDigest != target.SystemSafetyControlDigest ||
			command.AuthorizedControlRequestID != "" {
			return safety.ErrInvalidAuthority
		}
	}
	return nil
}

func insertFanoutVersion(
	ctx context.Context,
	repository *tenantRepository,
	snapshot safety.FanoutSnapshot,
) error {
	_, err := repository.queries.InsertAgentRunControlFanoutVersion(
		ctx,
		agentdb.InsertAgentRunControlFanoutVersionParams{
			TenantID: string(snapshot.TenantID), WorkOrderID: snapshot.WorkOrderID,
			FanoutID: snapshot.FanoutID, FanoutVersion: snapshot.FanoutVersion,
			PreviousFanoutVersion: previousVersion(snapshot.FanoutVersion),
			PreviousFanoutDigest:  optional(snapshot.PreviousFanoutDigest),
			FanoutDigest:          snapshot.FanoutDigest, Action: string(snapshot.Action),
			AuthorityKind: string(snapshot.AuthorityKind), AuthorityID: snapshot.AuthorityID,
			AuthorityDigest: snapshot.AuthorityDigest, CreatedAt: timestamp(snapshot.CreatedAt),
			UpdatedAt: timestamp(snapshot.UpdatedAt),
		},
	)
	if err != nil {
		return classifyControlWrite("insert fanout version", err)
	}
	for _, target := range snapshot.Targets {
		_, err := repository.queries.InsertAgentRunControlFanoutTargetVersion(
			ctx,
			agentdb.InsertAgentRunControlFanoutTargetVersionParams{
				TenantID: string(snapshot.TenantID), FanoutID: snapshot.FanoutID,
				FanoutVersion: snapshot.FanoutVersion, AuthorityKind: string(snapshot.AuthorityKind),
				AgentRunID: target.AgentRunID, RuntimeRunID: target.RuntimeRunID,
				TargetFencingToken:        target.TargetFencingToken,
				SystemSafetyControlID:     optional(target.SystemSafetyControlID),
				SystemSafetyControlDigest: optional(target.SystemSafetyControlDigest),
				ControlState:              string(target.ControlState),
			},
		)
		if err != nil {
			return classifyControlWrite("insert fanout target version", err)
		}
	}
	return nil
}

func previousVersion(version int64) *int64 {
	if version <= 1 {
		return nil
	}
	previous := version - 1
	return &previous
}

func fanoutSnapshotFromRows(
	root agentdb.AgentRunControlFanout,
	rows []agentdb.AgentRunControlFanoutTarget,
	updatedAt time.Time,
) safety.FanoutSnapshot {
	targets := make([]safety.FanoutTarget, 0, len(rows))
	for _, row := range rows {
		target := safety.FanoutTarget{
			AgentRunID: row.AgentRunID, RuntimeRunID: row.RuntimeRunID,
			TargetFencingToken: row.TargetFencingToken, CommandID: row.CommandID,
			ControlState: safety.ControlState(row.ControlState),
		}
		if row.SystemSafetyControlID != nil {
			target.SystemSafetyControlID = *row.SystemSafetyControlID
		}
		if row.SystemSafetyControlDigest != nil {
			target.SystemSafetyControlDigest = *row.SystemSafetyControlDigest
		}
		targets = append(targets, target)
	}
	snapshot := safety.FanoutSnapshot{
		FanoutID: root.FanoutID, TenantID: tenancy.TenantID(root.TenantID),
		WorkOrderID: root.WorkOrderID, Action: safety.Action(root.Action),
		AuthorityKind: safety.FanoutAuthorityKind(root.AuthorityKind),
		AuthorityID:   root.AuthorityID, AuthorityDigest: root.AuthorityDigest,
		Targets: targets, CreatedAt: root.CreatedAt.Time, UpdatedAt: updatedAt,
	}
	if root.SafetyEvidenceContractID != nil {
		snapshot.SafetyEvidenceContractID = *root.SafetyEvidenceContractID
	}
	return snapshot
}

func mapClaimedFanoutTarget(
	row agentdb.AgentRunControlFanoutTarget,
	tenantID tenancy.TenantID,
	workerID string,
) (safety.ClaimedFanoutTarget, error) {
	if row.ClaimWorkerID == nil || !row.ClaimExpiresAt.Valid || *row.ClaimWorkerID != workerID ||
		row.TenantID != string(tenantID) {
		return safety.ClaimedFanoutTarget{}, safety.ErrFanoutLeaseLost
	}
	claimed := safety.ClaimedFanoutTarget{
		TenantID: tenancy.TenantID(row.TenantID), WorkOrderID: row.WorkOrderID,
		FanoutID: row.FanoutID, AgentRunID: row.AgentRunID, RuntimeRunID: row.RuntimeRunID,
		TargetFencingToken: row.TargetFencingToken, CommandID: row.CommandID,
		ControlState:      safety.ControlState(row.ControlState),
		ClaimFencingToken: row.ClaimFencingToken, WorkerID: *row.ClaimWorkerID,
		LeaseExpiresAt: row.ClaimExpiresAt.Time,
	}
	if row.SystemSafetyControlID != nil {
		claimed.SystemSafetyControlID = *row.SystemSafetyControlID
	}
	if row.SystemSafetyControlDigest != nil {
		claimed.SystemSafetyControlDigest = *row.SystemSafetyControlDigest
	}
	return claimed, nil
}

func isTerminalWorkOrderState(state string) bool {
	return state == "completed" || state == "partial" || state == "failed" || state == "cancelled"
}
