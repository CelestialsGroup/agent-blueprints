package temporaladapter

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

// WorkflowInput contains only bounded control identity suitable for Temporal History.
type WorkflowInput struct {
	TenantID            string        `json:"tenant_id"`
	WorkOrderID         string        `json:"work_order_id"`
	WorkflowRunID       string        `json:"workflow_run_id"`
	WorkflowExecutionID string        `json:"workflow_execution_id"`
	WorkflowID          string        `json:"workflow_id"`
	WorkflowVersion     string        `json:"workflow_version"`
	DefinitionBuildID   string        `json:"definition_build_id"`
	DefinitionDigest    string        `json:"definition_digest"`
	EngineVersion       string        `json:"engine_version"`
	WorkerDeployment    string        `json:"worker_deployment"`
	WorkerBuildID       string        `json:"worker_build_id"`
	StartIdentityDigest string        `json:"start_identity_digest"`
	CreatedAt           time.Time     `json:"created_at"`
	ActivitySchedule    time.Duration `json:"activity_schedule_timeout"`
	ActivityStart       time.Duration `json:"activity_start_timeout"`
	StartConfirmed      bool          `json:"start_confirmed"`
	Generation          int           `json:"generation"`
}

func (input WorkflowInput) validate() error {
	identifiers := []struct {
		name  string
		value string
	}{
		{"tenant ID", input.TenantID},
		{"WorkOrder ID", input.WorkOrderID},
		{"WorkflowRun ID", input.WorkflowRunID},
		{"workflow execution ID", input.WorkflowExecutionID},
		{"workflow ID", input.WorkflowID},
		{"workflow version", input.WorkflowVersion},
		{"definition build ID", input.DefinitionBuildID},
		{"definition digest", input.DefinitionDigest},
		{"engine version", input.EngineVersion},
		{"worker deployment", input.WorkerDeployment},
		{"worker build ID", input.WorkerBuildID},
		{"start identity digest", input.StartIdentityDigest},
	}
	for _, identifier := range identifiers {
		if err := validateIdentifier(identifier.value); err != nil {
			return fmt.Errorf("invalid %s: %w", identifier.name, err)
		}
	}
	if input.CreatedAt.IsZero() || input.CreatedAt.Location() != time.UTC ||
		!input.CreatedAt.Equal(input.CreatedAt.Truncate(time.Microsecond)) {
		return fmt.Errorf("created_at must use UTC PostgreSQL microsecond precision")
	}
	if input.ActivitySchedule <= 0 || input.ActivitySchedule > 10*time.Minute ||
		input.ActivityStart <= 0 || input.ActivityStart > input.ActivitySchedule {
		return fmt.Errorf("activity timeouts are outside the supported range")
	}
	if input.Generation < 0 || input.Generation > maxContinueAsNewGeneration {
		return fmt.Errorf("continue-as-new generation is outside the supported range")
	}
	return nil
}

// WorkOrderWorkflow confirms the stable WorkflowRun once, then waits for bounded
// orchestration control. Continue-as-New preserves the Platform WorkflowRun.
func WorkOrderWorkflow(ctx workflow.Context, input WorkflowInput) error {
	if err := input.validate(); err != nil {
		return temporal.NewNonRetryableApplicationError(
			"invalid WorkOrder Workflow input", "invalid_workflow_input", err,
		)
	}
	if !input.StartConfirmed {
		activityOptions := workflow.ActivityOptions{
			ScheduleToCloseTimeout: input.ActivitySchedule,
			StartToCloseTimeout:    input.ActivityStart,
			RetryPolicy: &temporal.RetryPolicy{
				InitialInterval:    time.Second,
				BackoffCoefficient: 2,
				MaximumInterval:    30 * time.Second,
				MaximumAttempts:    10,
			},
		}
		activityCtx := workflow.WithActivityOptions(ctx, activityOptions)
		if err := workflow.ExecuteActivity(activityCtx, ConfirmStartActivityType, input).Get(ctx, nil); err != nil {
			return err
		}
		input.StartConfirmed = true
	}

	var command string
	workflow.GetSignalChannel(ctx, ControlSignal).Receive(ctx, &command)
	switch command {
	case ControlComplete:
		return nil
	case ControlContinueAsNew:
		if input.Generation >= maxContinueAsNewGeneration {
			return temporal.NewNonRetryableApplicationError(
				"continue-as-new generation limit reached", "generation_limit", nil,
			)
		}
		input.Generation++
		return workflow.NewContinueAsNewError(ctx, WorkflowType, input)
	default:
		return temporal.NewNonRetryableApplicationError(
			"unsupported orchestration control", "unsupported_control", nil,
		)
	}
}
