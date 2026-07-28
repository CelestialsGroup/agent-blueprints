package temporaladapter

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	commonpb "go.temporal.io/api/common/v1"
	"go.temporal.io/api/serviceerror"
	workflowpb "go.temporal.io/api/workflow/v1"
	workflowservice "go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/converter"

	domain "github.com/shell-echo/agent/internal/domain/orchestration"
)

func TestStarterCreatesStableWorkflow(t *testing.T) {
	request := testStartRequest()
	config := testConfig()
	temporalWorkflowID, err := workflowID(request.WorkOrderID)
	if err != nil {
		t.Fatal(err)
	}
	fake := &fakeStartClient{run: fakeWorkflowRun{id: temporalWorkflowID, runID: "native-run-a"}}
	starter, err := NewStarter(fake, config)
	if err != nil {
		t.Fatalf("create starter: %v", err)
	}
	receipt, err := starter.Start(context.Background(), request)
	if err != nil {
		t.Fatalf("start workflow: %v", err)
	}
	if receipt.Outcome != domain.StartCreated || receipt.WorkflowRunID != request.WorkflowRunID {
		t.Fatalf("unexpected receipt: %#v", receipt)
	}
	if fake.options.ID != temporalWorkflowID || fake.workflow != WorkflowType {
		t.Fatalf("unstable execution identity: options=%#v workflow=%v", fake.options, fake.workflow)
	}
	if fake.options.WorkflowExecutionErrorWhenAlreadyStarted != true ||
		fake.options.WorkflowIDReusePolicy.String() != "RejectDuplicate" ||
		fake.options.WorkflowIDConflictPolicy.String() != "Fail" {
		t.Fatalf("unsafe start policies: %#v", fake.options)
	}
	input, ok := fake.args[0].(WorkflowInput)
	if !ok || input.StartIdentityDigest == "" || input.StartConfirmed {
		t.Fatalf("invalid Workflow input: %#v", fake.args)
	}
	if strings.Contains(receipt.NativeExecutionReferenceDigest, "native-run-a") {
		t.Fatal("receipt leaked native Run ID")
	}
}

func TestStarterReconcilesCompatibleDuplicateAndRejectsConflict(t *testing.T) {
	request := testStartRequest()
	config := testConfig()
	temporalWorkflowID, _ := workflowID(request.WorkOrderID)
	digest, err := startIdentityDigest(request, config, temporalWorkflowID)
	if err != nil {
		t.Fatal(err)
	}
	fake := &fakeStartClient{
		executeErr:  serviceerror.NewWorkflowExecutionAlreadyStarted("exists", "request", "native-run-a"),
		description: workflowDescription(t, temporalWorkflowID, "native-run-a", digest),
	}
	starter, _ := NewStarter(fake, config)
	receipt, err := starter.Start(context.Background(), request)
	if err != nil {
		t.Fatalf("reconcile compatible start: %v", err)
	}
	if receipt.Outcome != domain.StartReconciled || fake.describeCalls != 1 {
		t.Fatalf("unexpected reconciliation: receipt=%#v calls=%d", receipt, fake.describeCalls)
	}

	fake.description = workflowDescription(t, temporalWorkflowID, "native-run-a", "sha256:"+strings.Repeat("f", 64))
	if _, err := starter.Start(context.Background(), request); !errors.Is(err, ErrStartConflict) {
		t.Fatalf("conflicting start error = %v, want ErrStartConflict", err)
	}
}

func TestStarterClassifiesUnknownAndRejectedStarts(t *testing.T) {
	request := testStartRequest()
	config := testConfig()
	tests := []struct {
		name       string
		executeErr error
		want       error
	}{
		{"unknown timeout", context.DeadlineExceeded, ErrStartOutcomeUnknown},
		{"invalid request", serviceerror.NewInvalidArgument("invalid"), ErrStartFailed},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			fake := &fakeStartClient{executeErr: test.executeErr, describeErr: serviceerror.NewNotFound("missing")}
			starter, _ := NewStarter(fake, config)
			if _, err := starter.Start(context.Background(), request); !errors.Is(err, test.want) {
				t.Fatalf("Start() error = %v, want %v", err, test.want)
			}
		})
	}
}

func TestStarterReconcilesOrRejectsInvalidSuccessHandle(t *testing.T) {
	request := testStartRequest()
	config := testConfig()
	temporalWorkflowID, _ := workflowID(request.WorkOrderID)
	digest, err := startIdentityDigest(request, config, temporalWorkflowID)
	if err != nil {
		t.Fatal(err)
	}

	fake := &fakeStartClient{
		run:         fakeWorkflowRun{id: "unexpected-workflow", runID: "unexpected-run"},
		description: workflowDescription(t, temporalWorkflowID, "native-run-a", digest),
	}
	starter, _ := NewStarter(fake, config)
	receipt, err := starter.Start(context.Background(), request)
	if err != nil || receipt.Outcome != domain.StartReconciled || fake.describeCalls != 1 {
		t.Fatalf("mismatched handle reconciliation = %#v, %v, calls=%d", receipt, err, fake.describeCalls)
	}

	fake = &fakeStartClient{describeErr: serviceerror.NewNotFound("missing")}
	starter, _ = NewStarter(fake, config)
	if _, err := starter.Start(context.Background(), request); !errors.Is(err, ErrStartOutcomeUnknown) {
		t.Fatalf("missing success handle error = %v, want ErrStartOutcomeUnknown", err)
	}
}

func testStartRequest() domain.StartRequest {
	return domain.StartRequest{
		TenantID: "tenant-a", WorkOrderID: "work-order-a",
		WorkflowRunID: "workflow-run-a", WorkflowExecutionID: "workflow-execution-a",
		Workflow: domain.WorkflowDefinition{
			ID: "workflow.agent-execution", Version: "1.0.0",
			DefinitionBuildID: "workflow-definition-b03.1",
			DefinitionDigest:  "sha256:" + strings.Repeat("1", 64),
		},
		CreatedAt: time.Date(2026, 7, 28, 1, 2, 3, 123456000, time.UTC),
	}
}

func workflowDescription(
	t *testing.T,
	workflowIDValue string,
	runID string,
	digest string,
) *workflowservice.DescribeWorkflowExecutionResponse {
	t.Helper()
	payload, err := converter.GetDefaultDataConverter().ToPayload(digest)
	if err != nil {
		t.Fatalf("encode memo: %v", err)
	}
	return &workflowservice.DescribeWorkflowExecutionResponse{
		WorkflowExecutionInfo: &workflowpb.WorkflowExecutionInfo{
			Execution: &commonpb.WorkflowExecution{WorkflowId: workflowIDValue, RunId: runID},
			Type:      &commonpb.WorkflowType{Name: WorkflowType},
			Memo:      &commonpb.Memo{Fields: map[string]*commonpb.Payload{StartIdentityMemoKey: payload}},
		},
	}
}

type fakeStartClient struct {
	run           client.WorkflowRun
	executeErr    error
	description   *workflowservice.DescribeWorkflowExecutionResponse
	describeErr   error
	describeCalls int
	options       client.StartWorkflowOptions
	workflow      interface{}
	args          []interface{}
}

func (fake *fakeStartClient) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	workflow interface{},
	args ...interface{},
) (client.WorkflowRun, error) {
	fake.options = options
	fake.workflow = workflow
	fake.args = args
	return fake.run, fake.executeErr
}

func (fake *fakeStartClient) DescribeWorkflowExecution(
	context.Context,
	string,
	string,
) (*workflowservice.DescribeWorkflowExecutionResponse, error) {
	fake.describeCalls++
	return fake.description, fake.describeErr
}

type fakeWorkflowRun struct {
	id    string
	runID string
}

func (run fakeWorkflowRun) GetID() string                      { return run.id }
func (run fakeWorkflowRun) GetRunID() string                   { return run.runID }
func (fakeWorkflowRun) Get(context.Context, interface{}) error { return nil }
func (fakeWorkflowRun) GetWithOptions(context.Context, interface{}, client.WorkflowRunGetOptions) error {
	return nil
}
