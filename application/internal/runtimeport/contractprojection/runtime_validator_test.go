package contractprojection

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/shell-echo/agent/internal/runtimeport"
)

const (
	lockedRegistryDigest = "sha256:eaae5ff3a467b85bbb5bb1cdbba4dd4b5546d7f5fb1cb1c17e37565bec55ae8c"
	testTokenBytes       = "validator.header.payload.signature"
)

func TestRuntimeDocumentValidatorAcceptsLockedMutationExamples(t *testing.T) {
	validator := testRuntimeDocumentValidator(t)
	for _, item := range []struct {
		operation runtimeport.Operation
		path      string
		digest    string
	}{
		{runtimeport.OperationStart, "agent-runtime-start-request.json", "request_digest"},
		{runtimeport.OperationCommand, "agent-runtime-command.json", "command_digest"},
	} {
		t.Run(string(item.operation), func(t *testing.T) {
			encoded := contractExample(t, item.path)
			invocation := invocationFromDocument(t, item.operation, encoded, item.digest)
			if err := validator.ValidateMutationRequest(item.operation, invocation, encoded); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestRuntimeDocumentValidatorRejectsStructuralAndBindingDrift(t *testing.T) {
	validator := testRuntimeDocumentValidator(t)
	encoded := contractExample(t, "agent-runtime-command.json")
	invocation := invocationFromDocument(t, runtimeport.OperationCommand, encoded, "command_digest")

	var document map[string]any
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	document["runtime_run_id"] = "different-runtime-run"
	drifted, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if err := validator.ValidateMutationRequest(runtimeport.OperationCommand, invocation, drifted); !errors.Is(err, ErrInvalidRuntimeDocument) {
		t.Fatalf("binding drift error = %v", err)
	}
	duplicate := []byte(`{"code":"ABC","code":"DEF","message":"x","retryable":false,"trace_id":"t"}`)
	if err := validator.ValidateErrorResponse(duplicate); !errors.Is(err, ErrInvalidRuntimeDocument) {
		t.Fatalf("duplicate member error = %v", err)
	}
	trailing := append(contractExample(t, "agent-runtime-run-status.json"), []byte(" true")...)
	if err := validator.ValidateSuccessResponse(runtimeport.OperationReadStatus, trailing); !errors.Is(err, ErrInvalidRuntimeDocument) {
		t.Fatalf("trailing content error = %v", err)
	}
	for name, encoded := range map[string][]byte{
		"invalid UTF-8":      {'{', '"', 'x', '"', ':', '"', 0xff, '"', '}'},
		"depth bound":        []byte(`[[[[]]]]`),
		"node bound":         []byte(`[true,false,null]`),
		"number token bound": []byte(`{"n":12345}`),
	} {
		t.Run(name, func(t *testing.T) {
			limits := validator.limits
			switch name {
			case "depth bound":
				limits.MaxDepth = 2
			case "node bound":
				limits.MaxNodes = 3
			case "number token bound":
				limits.MaxNumberTokenBytes = 4
			}
			if err := validateJSONStructure(encoded, limits); !errors.Is(err, ErrInvalidRuntimeDocument) {
				t.Fatalf("structure error = %v", err)
			}
		})
	}
}

func TestRuntimeDocumentValidatorBindsSchemaAndEventRegistry(t *testing.T) {
	validator := testRuntimeDocumentValidator(t)
	capabilities := contractExample(t, "agent-runtime-capabilities.json")
	if err := validator.ValidateSuccessResponse(runtimeport.OperationCapabilities, capabilities); err != nil {
		t.Fatal(err)
	}
	var drifted map[string]any
	if err := json.Unmarshal(capabilities, &drifted); err != nil {
		t.Fatal(err)
	}
	registries := drifted["event_registries"].([]any)
	registries[0].(map[string]any)["registry_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	encoded, err := json.Marshal(drifted)
	if err != nil {
		t.Fatal(err)
	}
	if err := validator.ValidateSuccessResponse(runtimeport.OperationCapabilities, encoded); !errors.Is(err, ErrRegistryBindingMismatch) {
		t.Fatalf("registry drift error = %v", err)
	}

	events := contractExample(t, "agent-runtime-event-page.json")
	if err := validator.ValidateSuccessResponse(runtimeport.OperationReadEvents, events); err != nil {
		t.Fatal(err)
	}
	var invalid map[string]any
	if err := json.Unmarshal(events, &invalid); err != nil {
		t.Fatal(err)
	}
	event := invalid["events"].([]any)[0].(map[string]any)
	event["data"] = map[string]any{"unexpected": true}
	invalidEvent, err := json.Marshal(invalid)
	if err != nil {
		t.Fatal(err)
	}
	if err := validator.ValidateSuccessResponse(runtimeport.OperationReadEvents, invalidEvent); !errors.Is(err, ErrInvalidRuntimeDocument) {
		t.Fatalf("typed Event data error = %v", err)
	}
}

func TestRuntimeDocumentValidatorRejectsInvalidRegistryBinding(t *testing.T) {
	digest, err := runtimeport.NewDigest(lockedRegistryDigest)
	if err != nil {
		t.Fatal(err)
	}
	for name, binding := range map[string]RuntimeEventRegistryBinding{
		"empty ID":       {Version: 1, Digest: digest},
		"NUL ID":         {ID: "agent-runtime\x00core", Version: 1, Digest: digest},
		"unsafe version": {ID: "agent-runtime-core", Version: runtimeport.MaxSafeInteger + 1, Digest: digest},
		"missing digest": {ID: "agent-runtime-core", Version: 1},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := NewRuntimeDocumentValidator(schemaDocuments(t), testDocumentLimits(), binding); !errors.Is(err, ErrRegistryBindingMismatch) {
				t.Fatalf("error = %v", err)
			}
		})
	}
}

func testRuntimeDocumentValidator(t *testing.T) *RuntimeDocumentValidator {
	t.Helper()
	digest, err := runtimeport.NewDigest(lockedRegistryDigest)
	if err != nil {
		t.Fatal(err)
	}
	validator, err := NewRuntimeDocumentValidator(
		schemaDocuments(t),
		testDocumentLimits(),
		RuntimeEventRegistryBinding{ID: "agent-runtime-core", Version: 1, Digest: digest},
	)
	if err != nil {
		t.Fatal(err)
	}
	return validator
}

func testDocumentLimits() DocumentLimits {
	return DocumentLimits{MaxBytes: 8 * 1024 * 1024, MaxDepth: 64, MaxNodes: 100_000, MaxNumberTokenBytes: 1024}
}

func contractExample(t *testing.T, name string) []byte {
	t.Helper()
	encoded, err := os.ReadFile(filepath.Join(contractRoot(t), "examples", "contracts", name))
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func invocationFromDocument(
	t *testing.T,
	operation runtimeport.Operation,
	encoded []byte,
	digestField string,
) runtimeport.Invocation {
	t.Helper()
	var document struct {
		RuntimeRunID        string `json:"runtime_run_id"`
		InvocationID        string `json:"invocation_id"`
		InvocationAttemptID string `json:"invocation_attempt_id"`
		FencingToken        uint64 `json:"fencing_token"`
		RequestDigest       string `json:"request_digest"`
		CommandDigest       string `json:"command_digest"`
	}
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	digestValue := document.RequestDigest
	if digestField == "command_digest" {
		digestValue = document.CommandDigest
	}
	digest, err := runtimeport.NewDigest(digestValue)
	if err != nil {
		t.Fatal(err)
	}
	token, err := runtimeport.NewInvocationToken([]byte(testTokenBytes), 128)
	if err != nil {
		t.Fatal(err)
	}
	invocation, err := runtimeport.NewInvocation(
		operation,
		"apr_01J00000000000000000000000",
		document.RuntimeRunID,
		document.InvocationID,
		document.InvocationAttemptID,
		document.FencingToken,
		digest,
		token,
	)
	if err != nil {
		t.Fatal(err)
	}
	return invocation
}
