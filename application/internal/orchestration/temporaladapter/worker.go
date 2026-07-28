package temporaladapter

import (
	"context"
	"errors"
	"fmt"

	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
)

// NewWorker assembles the versioned worker without starting network polling.
func NewWorker(
	temporalClient client.Client,
	config Config,
	activities *Activities,
) (worker.Worker, error) {
	if temporalClient == nil {
		return nil, errors.New("temporal client is required")
	}
	if activities == nil {
		return nil, errors.New("orchestration Activities are required")
	}
	if err := config.Validate(); err != nil {
		return nil, err
	}
	result := worker.New(temporalClient, config.TaskQueue, worker.Options{
		MaxConcurrentWorkflowTaskExecutionSize: config.MaxWorkflowTasks,
		MaxConcurrentActivityExecutionSize:     config.MaxActivityTasks,
		WorkerStopTimeout:                      config.WorkerStop,
		DisableRegistrationAliasing:            true,
		DeploymentOptions: worker.DeploymentOptions{
			UseVersioning: true,
			Version: worker.WorkerDeploymentVersion{
				DeploymentName: config.WorkerDeployment,
				BuildID:        config.WorkerBuildID,
			},
			DefaultVersioningBehavior: workflow.VersioningBehaviorPinned,
		},
	})
	result.RegisterWorkflowWithOptions(WorkOrderWorkflow, workflow.RegisterOptions{
		Name: WorkflowType, VersioningBehavior: workflow.VersioningBehaviorPinned,
	})
	result.RegisterActivityWithOptions(activities.ConfirmStart, activity.RegisterOptions{
		Name: ConfirmStartActivityType,
	})
	return result, nil
}

// RunWorker polls until cancellation and then performs the SDK's bounded drain.
func RunWorker(ctx context.Context, temporalWorker worker.Worker) error {
	if temporalWorker == nil {
		return errors.New("temporal worker is required")
	}
	if err := temporalWorker.Start(); err != nil {
		return fmt.Errorf("start Temporal worker: %w", err)
	}
	<-ctx.Done()
	temporalWorker.Stop()
	return nil
}
