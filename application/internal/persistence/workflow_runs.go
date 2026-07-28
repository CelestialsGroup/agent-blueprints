package persistence

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/shell-echo/agent/internal/domain/orchestration"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/generated/agentdb"
)

// WorkflowRunRepository persists the immutable PostgreSQL confirmation of a
// durable orchestration start. Calling it does not start or contact Temporal.
type WorkflowRunRepository struct {
	runner *TransactionRunner
}

func NewWorkflowRunRepository(runner *TransactionRunner) (*WorkflowRunRepository, error) {
	if runner == nil {
		return nil, errors.New("transaction runner is required")
	}
	return &WorkflowRunRepository{runner: runner}, nil
}

// Get returns one Tenant-qualified WorkflowRun without exposing sqlc or pgx values.
func (repository *WorkflowRunRepository) Get(
	ctx context.Context,
	tenantID tenancy.TenantID,
	workflowRunID string,
) (orchestration.WorkflowRun, error) {
	if err := orchestration.ValidateWorkflowRunID(workflowRunID); err != nil {
		return orchestration.WorkflowRun{}, err
	}
	var result orchestration.WorkflowRun
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		row, err := txRepository.queries.GetWorkflowRunByID(ctx, agentdb.GetWorkflowRunByIDParams{
			TenantID: string(tenantID), WorkflowRunID: workflowRunID,
		})
		if errors.Is(err, pgx.ErrNoRows) {
			return orchestration.ErrWorkflowRunNotFound
		}
		if err != nil {
			return fmt.Errorf("read WorkflowRun: %w", err)
		}
		result, err = mapWorkflowRun(row)
		return err
	})
	return result, err
}

// ConfirmWorkflowStart appends one immutable WorkflowRun after the caller has
// confirmed the durable orchestration execution. The same complete fact is a
// replay; reusing its WorkflowRun, WorkOrder, or binding identity for different
// content fails closed.
func (repository *WorkflowRunRepository) ConfirmWorkflowStart(
	ctx context.Context,
	tenantID tenancy.TenantID,
	run orchestration.WorkflowRun,
) (orchestration.ConfirmOutcome, error) {
	run.CreatedAt = orchestration.DatabaseTime(run.CreatedAt)
	if err := run.Validate(tenantID); err != nil {
		return "", err
	}

	var outcome orchestration.ConfirmOutcome
	err := repository.runner.run(ctx, tenantID, func(ctx context.Context, txRepository *tenantRepository) error {
		workOrder, err := txRepository.queries.LockWorkOrder(ctx, agentdb.LockWorkOrderParams{
			TenantID: string(tenantID), WorkOrderID: run.WorkOrderID,
		})
		if errors.Is(err, pgx.ErrNoRows) {
			return orchestration.ErrStartAuthority
		}
		if err != nil {
			return fmt.Errorf("lock WorkflowRun WorkOrder: %w", err)
		}

		existing, found, err := findExistingWorkflowRun(ctx, txRepository, tenantID, run)
		if err != nil {
			return err
		}
		if found {
			if !existing.Matches(run) {
				return orchestration.ErrWorkflowRunConflict
			}
			outcome = orchestration.ConfirmReplay
			return nil
		}

		if workOrder.CreatedAt.Time.After(run.CreatedAt) || terminalWorkOrderState(workOrder.State) {
			return orchestration.ErrStartAuthority
		}

		row, err := txRepository.queries.InsertWorkflowRun(ctx, workflowRunParams(run))
		if err == nil {
			persisted, mapErr := mapWorkflowRun(row)
			if mapErr != nil {
				return mapErr
			}
			if !persisted.Matches(run) {
				return fmt.Errorf("%w: inserted WorkflowRun changed", orchestration.ErrWorkflowRunConflict)
			}
			outcome = orchestration.ConfirmInserted
			return nil
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return classifyWorkflowRunWrite(err)
		}

		// ON CONFLICT covers global identity and binding collisions, including
		// rows hidden by another Tenant's RLS policy. Re-read only visible rows
		// to recognize a legitimate same-Tenant replay without enumerating the
		// conflicting identity across Tenant boundaries.
		existing, found, err = findExistingWorkflowRun(ctx, txRepository, tenantID, run)
		if err != nil {
			return err
		}
		if !found || !existing.Matches(run) {
			return orchestration.ErrWorkflowRunConflict
		}
		outcome = orchestration.ConfirmReplay
		return nil
	})
	return outcome, err
}

func findExistingWorkflowRun(
	ctx context.Context,
	repository *tenantRepository,
	tenantID tenancy.TenantID,
	run orchestration.WorkflowRun,
) (orchestration.WorkflowRun, bool, error) {
	row, err := repository.queries.GetWorkflowRunByID(ctx, agentdb.GetWorkflowRunByIDParams{
		TenantID: string(tenantID), WorkflowRunID: run.WorkflowRunID,
	})
	if err == nil {
		value, mapErr := mapWorkflowRun(row)
		return value, true, mapErr
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return orchestration.WorkflowRun{}, false, fmt.Errorf("read WorkflowRun identity: %w", err)
	}

	row, err = repository.queries.GetWorkflowRunByWorkOrderID(ctx, agentdb.GetWorkflowRunByWorkOrderIDParams{
		TenantID: string(tenantID), WorkOrderID: run.WorkOrderID,
	})
	if err == nil {
		value, mapErr := mapWorkflowRun(row)
		return value, true, mapErr
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return orchestration.WorkflowRun{}, false, nil
	}
	return orchestration.WorkflowRun{}, false, fmt.Errorf("read WorkOrder WorkflowRun binding: %w", err)
}

func workflowRunParams(run orchestration.WorkflowRun) agentdb.InsertWorkflowRunParams {
	return agentdb.InsertWorkflowRunParams{
		TenantID:                       string(run.TenantID),
		WorkflowRunID:                  run.WorkflowRunID,
		WorkOrderID:                    run.WorkOrderID,
		WorkflowID:                     run.Workflow.ID,
		WorkflowVersion:                run.Workflow.Version,
		WorkflowDefinitionBuildID:      run.Workflow.DefinitionBuildID,
		WorkflowDefinitionDigest:       run.Workflow.DefinitionDigest,
		OrchestrationEngineID:          run.OrchestrationBinding.EngineID,
		OrchestrationEngineVersion:     run.OrchestrationBinding.EngineVersion,
		WorkflowExecutionID:            run.OrchestrationBinding.WorkflowExecutionID,
		NativeExecutionReferenceDigest: run.OrchestrationBinding.NativeExecutionReferenceDigest,
		WorkerDeployment:               run.OrchestrationBinding.WorkerDeployment,
		WorkerBuildID:                  run.OrchestrationBinding.WorkerBuildID,
		VersioningBehavior:             string(run.OrchestrationBinding.VersioningBehavior),
		OrchestrationBindingDigest:     run.OrchestrationBinding.BindingDigest,
		CreatedAt:                      timestamp(run.CreatedAt),
	}
}

func mapWorkflowRun(row agentdb.AgentWorkflowRun) (orchestration.WorkflowRun, error) {
	value := orchestration.WorkflowRun{
		WorkflowRunID: row.WorkflowRunID,
		TenantID:      tenancy.TenantID(row.TenantID),
		WorkOrderID:   row.WorkOrderID,
		Workflow: orchestration.WorkflowDefinition{
			ID:                row.WorkflowID,
			Version:           row.WorkflowVersion,
			DefinitionBuildID: row.WorkflowDefinitionBuildID,
			DefinitionDigest:  row.WorkflowDefinitionDigest,
		},
		OrchestrationBinding: orchestration.OrchestrationBinding{
			EngineID:                       row.OrchestrationEngineID,
			EngineVersion:                  row.OrchestrationEngineVersion,
			WorkflowExecutionID:            row.WorkflowExecutionID,
			NativeExecutionReferenceDigest: row.NativeExecutionReferenceDigest,
			WorkerDeployment:               row.WorkerDeployment,
			WorkerBuildID:                  row.WorkerBuildID,
			VersioningBehavior:             orchestration.VersioningBehavior(row.VersioningBehavior),
			BindingDigest:                  row.OrchestrationBindingDigest,
		},
		CreatedAt: row.CreatedAt.Time,
	}
	if !row.CreatedAt.Valid {
		return orchestration.WorkflowRun{}, fmt.Errorf("%w: persisted created_at", orchestration.ErrInvalidWorkflowRun)
	}
	if err := value.Validate(value.TenantID); err != nil {
		return orchestration.WorkflowRun{}, fmt.Errorf("map persisted WorkflowRun: %w", err)
	}
	return value, nil
}

func classifyWorkflowRunWrite(err error) error {
	var databaseError *pgconn.PgError
	if !errors.As(err, &databaseError) {
		return fmt.Errorf("append WorkflowRun: %w", err)
	}
	switch databaseError.Code {
	case "23503":
		return orchestration.ErrStartAuthority
	case "23505":
		return orchestration.ErrWorkflowRunConflict
	case "23514", "22001", "22007", "22008":
		return orchestration.ErrInvalidWorkflowRun
	default:
		return fmt.Errorf("append WorkflowRun: %w", err)
	}
}

func terminalWorkOrderState(state string) bool {
	switch state {
	case "completed", "partial", "failed", "cancelled":
		return true
	default:
		return false
	}
}
