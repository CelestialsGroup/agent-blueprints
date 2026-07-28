package temporaladapter

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/testsuite"
)

func TestWorkOrderWorkflowConfirmsThenCompletes(t *testing.T) {
	var suite testsuite.WorkflowTestSuite
	environment := suite.NewTestWorkflowEnvironment()
	confirmations := 0
	environment.RegisterActivityWithOptions(
		func(context.Context, WorkflowInput) error {
			confirmations++
			return nil
		},
		activity.RegisterOptions{Name: ConfirmStartActivityType},
	)
	environment.RegisterDelayedCallback(func() {
		environment.SignalWorkflow(ControlSignal, ControlComplete)
	}, time.Second)
	environment.ExecuteWorkflow(WorkOrderWorkflow, workflowInputForTest(t))
	if err := environment.GetWorkflowError(); err != nil {
		t.Fatalf("workflow failed: %v", err)
	}
	if confirmations != 1 {
		t.Fatalf("confirmations = %d, want 1", confirmations)
	}
}

func TestWorkOrderWorkflowSkipsConfirmationAfterContinueAsNew(t *testing.T) {
	var suite testsuite.WorkflowTestSuite
	environment := suite.NewTestWorkflowEnvironment()
	confirmations := 0
	environment.RegisterActivityWithOptions(
		func(context.Context, WorkflowInput) error {
			confirmations++
			return nil
		},
		activity.RegisterOptions{Name: ConfirmStartActivityType},
	)
	input := workflowInputForTest(t)
	input.StartConfirmed = true
	input.Generation = 1
	environment.RegisterDelayedCallback(func() {
		environment.SignalWorkflow(ControlSignal, ControlComplete)
	}, time.Second)
	environment.ExecuteWorkflow(WorkOrderWorkflow, input)
	if err := environment.GetWorkflowError(); err != nil {
		t.Fatalf("continued workflow failed: %v", err)
	}
	if confirmations != 0 {
		t.Fatalf("continued workflow repeated confirmation %d times", confirmations)
	}
}

func TestWorkflowInputValidationOrderIsDeterministic(t *testing.T) {
	input := workflowInputForTest(t)
	input.TenantID = ""
	input.WorkOrderID = ""
	for range 100 {
		if err := input.validate(); err == nil || !strings.Contains(err.Error(), "tenant ID") {
			t.Fatalf("first validation error = %v, want tenant ID", err)
		}
	}
}
