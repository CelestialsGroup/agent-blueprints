package replay_test

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"unicode/utf8"

	historypb "go.temporal.io/api/history/v1"
	"go.temporal.io/sdk/converter"
	temporallog "go.temporal.io/sdk/log"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
	"google.golang.org/protobuf/encoding/protojson"

	"github.com/shell-echo/agent/internal/orchestration/temporaladapter"
)

const completedFixture = "testdata/work-order-completed-v1.json"

func TestWorkOrderCompletedV1Replay(t *testing.T) {
	replayer := worker.NewWorkflowReplayer()
	replayer.RegisterWorkflowWithOptions(
		temporaladapter.WorkOrderWorkflow,
		workflow.RegisterOptions{
			Name:               temporaladapter.WorkflowType,
			VersioningBehavior: workflow.VersioningBehaviorPinned,
		},
	)
	logger := temporallog.NewStructuredLogger(slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err := replayer.ReplayWorkflowHistoryFromJSONFile(logger, completedFixture); err != nil {
		t.Fatalf("replay %s: %v", completedFixture, err)
	}
}

func TestWorkOrderCompletedV1SourceBindingAndPayloadHygiene(t *testing.T) {
	history := readFixture(t, completedFixture)
	input := initialWorkflowInput(t, history)

	workflowSource := filepath.Join("..", "..", "internal", "orchestration", "temporaladapter", "workflow.go")
	source, err := os.ReadFile(workflowSource)
	if err != nil {
		t.Fatalf("read Workflow definition source: %v", err)
	}
	digest := sha256.Sum256(source)
	wantDigest := "sha256:" + hex.EncodeToString(digest[:])
	if input.DefinitionDigest != wantDigest {
		t.Fatalf(
			"fixture definition_digest = %s, current Workflow source digest = %s; regenerate and review the fixture",
			input.DefinitionDigest,
			wantDigest,
		)
	}

	for eventIndex, event := range history.Events {
		encoded, err := protojson.Marshal(event)
		if err != nil {
			t.Fatalf("encode History event %d: %v", eventIndex+1, err)
		}
		var value any
		if err := json.Unmarshal(encoded, &value); err != nil {
			t.Fatalf("decode History event %d JSON: %v", eventIndex+1, err)
		}
		scanPayloadData(t, value, eventIndex+1)
	}
}

func readFixture(t *testing.T, path string) *historypb.History {
	t.Helper()
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read Replay fixture: %v", err)
	}
	history := &historypb.History{}
	if err := protojson.Unmarshal(encoded, history); err != nil {
		t.Fatalf("decode Replay fixture: %v", err)
	}
	if len(history.Events) == 0 {
		t.Fatal("Replay fixture contains no History events")
	}
	return history
}

func initialWorkflowInput(t *testing.T, history *historypb.History) temporaladapter.WorkflowInput {
	t.Helper()
	started := history.Events[0].GetWorkflowExecutionStartedEventAttributes()
	if started == nil || started.Input == nil || len(started.Input.Payloads) != 1 {
		t.Fatal("Replay fixture must begin with exactly one Workflow input payload")
	}
	var input temporaladapter.WorkflowInput
	if err := converter.GetDefaultDataConverter().FromPayload(started.Input.Payloads[0], &input); err != nil {
		t.Fatalf("decode initial WorkflowInput: %v", err)
	}
	return input
}

func scanPayloadData(t *testing.T, value any, eventIndex int) {
	t.Helper()
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if key == "data" {
				text, ok := child.(string)
				if !ok {
					t.Fatalf("History event %d payload data is not encoded text", eventIndex)
				}
				assertPayloadHygiene(t, eventIndex, text)
				continue
			}
			scanPayloadData(t, child, eventIndex)
		}
	case []any:
		for _, child := range typed {
			scanPayloadData(t, child, eventIndex)
		}
	}
}

func assertPayloadHygiene(t *testing.T, eventIndex int, encodedPayload string) {
	t.Helper()
	payload, err := base64.StdEncoding.DecodeString(encodedPayload)
	if err != nil {
		t.Fatalf("decode History event %d payload data: %v", eventIndex, err)
	}
	if len(payload) > 16*1024 || !utf8.Valid(payload) {
		t.Fatalf("History event %d payload is not bounded UTF-8 text", eventIndex)
	}
	lower := strings.ToLower(string(payload))
	for _, forbidden := range []string{
		"authorization", "bearer ", "credential", "endpoint", "password",
		"prompt", "secret", "token", "http://", "https://", "postgres://",
	} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("History event %d decoded payload contains forbidden term %q", eventIndex, forbidden)
		}
	}
}
