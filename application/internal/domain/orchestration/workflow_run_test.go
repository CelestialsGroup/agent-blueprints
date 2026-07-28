package orchestration

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

func TestLockedContractBindingDigestVector(t *testing.T) {
	binding := contractExampleBinding()
	digest, err := binding.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute binding digest: %v", err)
	}
	const want = "sha256:d6473b8bef35b020ece840bcfcf49c9e9f005d18329394dcc78f188fa20dfbbb"
	if digest != want {
		t.Fatalf("binding digest = %s, want %s", digest, want)
	}
	binding.BindingDigest = digest
	if err := binding.Validate(); err != nil {
		t.Fatalf("validate contract example binding: %v", err)
	}
}

func TestWorkflowRunValidation(t *testing.T) {
	run := validWorkflowRun(t)
	if err := run.Validate(run.TenantID); err != nil {
		t.Fatalf("validate WorkflowRun: %v", err)
	}

	tests := []struct {
		name   string
		mutate func(*WorkflowRun)
		want   error
	}{
		{"tenant mismatch", func(run *WorkflowRun) { run.TenantID = "tenant-b" }, ErrStartAuthority},
		{"NUL identifier", func(run *WorkflowRun) { run.WorkflowRunID = "workflow\x00run" }, ErrInvalidWorkflowRun},
		{"long identifier", func(run *WorkflowRun) { run.WorkOrderID = strings.Repeat("x", 201) }, ErrInvalidWorkflowRun},
		{"uppercase digest", func(run *WorkflowRun) { run.Workflow.DefinitionDigest = "sha256:" + strings.Repeat("A", 64) }, ErrInvalidWorkflowRun},
		{"binding mismatch", func(run *WorkflowRun) { run.OrchestrationBinding.WorkerBuildID = "other-build" }, ErrBindingDigestConflict},
		{"invalid versioning", func(run *WorkflowRun) {
			run.OrchestrationBinding.VersioningBehavior = "unversioned"
		}, ErrInvalidWorkflowRun},
		{"missing time", func(run *WorkflowRun) { run.CreatedAt = time.Time{} }, ErrInvalidWorkflowRun},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			candidate := run
			test.mutate(&candidate)
			if err := candidate.Validate(run.TenantID); !errors.Is(err, test.want) {
				t.Fatalf("Validate() error = %v, want %v", err, test.want)
			}
		})
	}
}

func TestWorkflowRunMatchesUsesDatabaseTime(t *testing.T) {
	run := validWorkflowRun(t)
	replayed := run
	replayed.CreatedAt = replayed.CreatedAt.Add(321 * time.Nanosecond)
	if !run.Matches(replayed) {
		t.Fatal("sub-microsecond timestamps should represent the same persisted fact")
	}
	replayed.WorkOrderID = "other-work-order"
	if run.Matches(replayed) {
		t.Fatal("different WorkOrder identity matched")
	}
}

func validWorkflowRun(t *testing.T) WorkflowRun {
	t.Helper()
	binding := contractExampleBinding()
	digest, err := binding.ExpectedDigest()
	if err != nil {
		t.Fatalf("compute binding digest: %v", err)
	}
	binding.BindingDigest = digest
	return WorkflowRun{
		WorkflowRunID: "workflow-run-a",
		TenantID:      tenancy.TenantID("tenant-a"),
		WorkOrderID:   "work-order-a",
		Workflow: WorkflowDefinition{
			ID: "workflow.agent-execution", Version: "2.0.0",
			DefinitionBuildID: "workflow-definition-2026-07-16.1",
			DefinitionDigest:  "sha256:" + strings.Repeat("2", 64),
		},
		OrchestrationBinding: binding,
		CreatedAt:            time.Date(2026, 7, 16, 9, 1, 0, 123456000, time.UTC),
	}
}

func contractExampleBinding() OrchestrationBinding {
	return OrchestrationBinding{
		EngineID:                       "temporal",
		EngineVersion:                  "1.27",
		WorkflowExecutionID:            "wfx_01J00000000000000000000000",
		NativeExecutionReferenceDigest: "sha256:1b53f2d19f0f50260f29dce5d878dde52b3624cd15c21b78713ad50c46b36f19",
		WorkerDeployment:               "agent-worker",
		WorkerBuildID:                  "worker-2026-07-16.1",
		VersioningBehavior:             VersioningPinned,
	}
}
