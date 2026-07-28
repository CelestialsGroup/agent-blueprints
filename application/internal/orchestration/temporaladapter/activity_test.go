package temporaladapter

import (
	"context"
	"strings"
	"testing"

	domain "github.com/shell-echo/agent/internal/domain/orchestration"
	"github.com/shell-echo/agent/internal/domain/tenancy"
)

func TestConfirmStartBuildsClosedWorkflowRun(t *testing.T) {
	confirmer := &recordingConfirmer{}
	activities, err := NewActivities(confirmer)
	if err != nil {
		t.Fatalf("create activities: %v", err)
	}
	input := workflowInputForTest(t)
	err = activities.confirmStart(context.Background(), input, nativeActivityInfo{
		Namespace: "agent-b03", WorkflowID: "work-order/work-order-a",
		RunID: "native-run-secret", WorkflowType: WorkflowType,
		TaskQueue: "agent-b03-work-orders",
	})
	if err != nil {
		t.Fatalf("confirm start: %v", err)
	}
	if confirmer.calls != 1 || confirmer.run.WorkflowRunID != input.WorkflowRunID {
		t.Fatalf("unexpected confirmation: %#v", confirmer)
	}
	if err := confirmer.run.Validate(confirmer.tenantID); err != nil {
		t.Fatalf("confirmation produced invalid WorkflowRun: %v", err)
	}
	if strings.Contains(confirmer.run.OrchestrationBinding.NativeExecutionReferenceDigest, "native-run-secret") {
		t.Fatal("persisted binding leaked native Run ID")
	}
}

func TestConfirmStartRejectsMismatchedNativeExecution(t *testing.T) {
	confirmer := &recordingConfirmer{}
	activities, _ := NewActivities(confirmer)
	err := activities.confirmStart(context.Background(), workflowInputForTest(t), nativeActivityInfo{
		Namespace: "agent-b03", WorkflowID: "work-order/other",
		RunID: "native-run", WorkflowType: WorkflowType, TaskQueue: "queue",
	})
	if err == nil || confirmer.calls != 0 {
		t.Fatalf("mismatched native execution error=%v calls=%d", err, confirmer.calls)
	}
}

func workflowInputForTest(t *testing.T) WorkflowInput {
	t.Helper()
	request := testStartRequest()
	config := testConfig()
	temporalWorkflowID, _ := workflowID(request.WorkOrderID)
	digest, err := startIdentityDigest(request, config, temporalWorkflowID)
	if err != nil {
		t.Fatal(err)
	}
	return WorkflowInput{
		TenantID: string(request.TenantID), WorkOrderID: request.WorkOrderID,
		WorkflowRunID: request.WorkflowRunID, WorkflowExecutionID: request.WorkflowExecutionID,
		WorkflowID: request.Workflow.ID, WorkflowVersion: request.Workflow.Version,
		DefinitionBuildID: request.Workflow.DefinitionBuildID,
		DefinitionDigest:  request.Workflow.DefinitionDigest,
		EngineVersion:     config.EngineVersion, WorkerDeployment: config.WorkerDeployment,
		WorkerBuildID: config.WorkerBuildID, StartIdentityDigest: digest,
		CreatedAt: request.CreatedAt, ActivitySchedule: config.ActivitySchedule,
		ActivityStart: config.ActivityStart,
	}
}

type recordingConfirmer struct {
	calls    int
	tenantID tenancy.TenantID
	run      domain.WorkflowRun
	err      error
}

func (confirmer *recordingConfirmer) ConfirmWorkflowStart(
	_ context.Context,
	tenantID tenancy.TenantID,
	run domain.WorkflowRun,
) (domain.ConfirmOutcome, error) {
	confirmer.calls++
	confirmer.tenantID = tenantID
	confirmer.run = run
	return domain.ConfirmInserted, confirmer.err
}
