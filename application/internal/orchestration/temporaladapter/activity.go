package temporaladapter

import (
	"context"
	"errors"
	"fmt"

	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/temporal"

	domain "github.com/shell-echo/agent/internal/domain/orchestration"
	"github.com/shell-echo/agent/internal/domain/tenancy"
)

type workflowRunConfirmer interface {
	ConfirmWorkflowStart(
		context.Context,
		tenancy.TenantID,
		domain.WorkflowRun,
	) (domain.ConfirmOutcome, error)
}

// Activities owns Temporal Activities for the bounded orchestration foundation.
type Activities struct {
	confirmer workflowRunConfirmer
}

// NewActivities binds Activities to the PostgreSQL-authoritative confirmer.
func NewActivities(confirmer workflowRunConfirmer) (*Activities, error) {
	if confirmer == nil {
		return nil, errors.New("WorkflowRun confirmer is required")
	}
	return &Activities{confirmer: confirmer}, nil
}

// ConfirmStart records a confirmed native execution in one tenant transaction.
func (activities *Activities) ConfirmStart(ctx context.Context, input WorkflowInput) error {
	info := activity.GetInfo(ctx)
	workflowType := ""
	if info.WorkflowType != nil {
		workflowType = info.WorkflowType.Name
	}
	return activities.confirmStart(ctx, input, nativeActivityInfo{
		Namespace:    info.Namespace,
		WorkflowID:   info.WorkflowExecution.ID,
		RunID:        info.WorkflowExecution.RunID,
		WorkflowType: workflowType,
		TaskQueue:    info.TaskQueue,
	})
}

type nativeActivityInfo struct {
	Namespace    string
	WorkflowID   string
	RunID        string
	WorkflowType string
	TaskQueue    string
}

func (activities *Activities) confirmStart(
	ctx context.Context,
	input WorkflowInput,
	info nativeActivityInfo,
) error {
	if err := input.validate(); err != nil {
		return nonRetryableConfirmationError("invalid confirmation input", err)
	}
	expectedWorkflowID, err := workflowID(input.WorkOrderID)
	if err != nil {
		return nonRetryableConfirmationError("invalid stable Workflow ID", err)
	}
	if info.WorkflowType != WorkflowType || info.WorkflowID != expectedWorkflowID ||
		info.TaskQueue == "" || info.Namespace == "" || info.RunID == "" {
		return nonRetryableConfirmationError(
			"native execution identity does not match confirmation input",
			errors.New("temporal workflow type, ID, queue, namespace, or Run ID is invalid"),
		)
	}
	nativeDigest, err := digestNativeExecution(info.Namespace, info.WorkflowID, info.RunID)
	if err != nil {
		return nonRetryableConfirmationError("invalid native execution reference", err)
	}
	binding := domain.OrchestrationBinding{
		EngineID: EngineID, EngineVersion: input.EngineVersion,
		WorkflowExecutionID:            input.WorkflowExecutionID,
		NativeExecutionReferenceDigest: nativeDigest,
		WorkerDeployment:               input.WorkerDeployment, WorkerBuildID: input.WorkerBuildID,
		VersioningBehavior: domain.VersioningBehavior(VersioningBehavior),
	}
	bindingDigest, err := binding.ExpectedDigest()
	if err != nil {
		return nonRetryableConfirmationError("derive orchestration binding digest", err)
	}
	binding.BindingDigest = bindingDigest
	run := domain.WorkflowRun{
		WorkflowRunID: input.WorkflowRunID,
		TenantID:      tenancy.TenantID(input.TenantID),
		WorkOrderID:   input.WorkOrderID,
		Workflow: domain.WorkflowDefinition{
			ID: input.WorkflowID, Version: input.WorkflowVersion,
			DefinitionBuildID: input.DefinitionBuildID,
			DefinitionDigest:  input.DefinitionDigest,
		},
		OrchestrationBinding: binding,
		CreatedAt:            input.CreatedAt,
	}
	if err := run.Validate(tenancy.TenantID(input.TenantID)); err != nil {
		return nonRetryableConfirmationError("invalid WorkflowRun confirmation", err)
	}
	if _, err := activities.confirmer.ConfirmWorkflowStart(
		ctx, tenancy.TenantID(input.TenantID), run,
	); err != nil {
		if isPermanentConfirmationError(err) {
			return nonRetryableConfirmationError("confirm WorkflowRun", err)
		}
		return fmt.Errorf("confirm WorkflowRun: %w", err)
	}
	return nil
}

func isPermanentConfirmationError(err error) bool {
	return errors.Is(err, domain.ErrInvalidWorkflowRun) ||
		errors.Is(err, domain.ErrBindingDigestConflict) ||
		errors.Is(err, domain.ErrWorkflowRunConflict) ||
		errors.Is(err, domain.ErrWorkflowRunNotFound) ||
		errors.Is(err, domain.ErrStartAuthority)
}

func nonRetryableConfirmationError(message string, cause error) error {
	return temporal.NewNonRetryableApplicationError(
		message, "workflow_run_confirmation_rejected", cause,
	)
}
