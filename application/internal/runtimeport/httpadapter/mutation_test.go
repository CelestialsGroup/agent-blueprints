package httpadapter

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/runtimeport"
)

func TestMutationOperationsDispatchExactBodyOnce(t *testing.T) {
	startBody := adapterContractExample(t, "agent-runtime-start-request.json")
	commandBody := adapterContractExample(t, "agent-runtime-command.json")
	statusBody := adapterContractExample(t, "agent-runtime-run-status.json")
	var requests atomic.Int64
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		if request.Method != http.MethodPost || request.ProtoMajor != 1 || request.ProtoMinor != 1 ||
			request.TLS == nil || len(request.TLS.PeerCertificates) != 1 ||
			request.Header.Get("Content-Type") != "application/json" || len(request.TransferEncoding) != 0 {
			t.Error("unexpected authenticated mutation request shape")
		}
		assertSingleBearer(t, request)
		encoded, err := io.ReadAll(request.Body)
		if err != nil {
			t.Error(err)
		}
		var expected []byte
		switch request.URL.RequestURI() {
		case "/v1/runs":
			expected = startBody
		case "/v1/runs/" + testRuntimeRunID + "/commands":
			expected = commandBody
		default:
			t.Errorf("unexpected target %q", request.URL.RequestURI())
		}
		if request.ContentLength != int64(len(expected)) || !bytes.Equal(encoded, expected) {
			t.Error("mutation body or Content-Length differs")
		}
		writeAdapterJSON(writer, http.StatusAccepted, statusBody)
	}))

	start := callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), testProviderRevisionID)
	assertAcceptedMutation(t, start, runtimeport.OperationStart)
	command := callMutation(t, adapter, runtimeport.OperationCommand, commandBody, testBearerToken, context.Background(), testProviderRevisionID)
	assertAcceptedMutation(t, command, runtimeport.OperationCommand)
	if requests.Load() != 2 {
		t.Fatalf("request count = %d", requests.Load())
	}
	t.Log("http-adapter-evidence:one-dispatch-exact-mutation-body:passed")
}

func TestMutationPreDispatchFailuresMakeZeroRequests(t *testing.T) {
	startBody := adapterContractExample(t, "agent-runtime-start-request.json")
	commandBody := adapterContractExample(t, "agent-runtime-command.json")
	invalidStart := mutateAdapterDocument(t, startBody, func(document map[string]any) {
		document["unexpected"] = true
	})
	oversizedCommand := append([]byte(nil), commandBody...)
	oversizedCommand = append(oversizedCommand, bytes.Repeat([]byte(" "), 262144-len(oversizedCommand)+1)...)
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	var requests atomic.Int64
	adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		requests.Add(1)
		writeAdapterJSON(writer, http.StatusAccepted, adapterContractExample(t, "agent-runtime-run-status.json"))
	}))
	for name, outcome := range map[string]runtimeport.MutationOutcome{
		"schema":       callMutation(t, adapter, runtimeport.OperationStart, invalidStart, testBearerToken, context.Background(), testProviderRevisionID),
		"token":        callMutation(t, adapter, runtimeport.OperationStart, startBody, "not-compact", context.Background(), testProviderRevisionID),
		"context":      callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, canceled, testProviderRevisionID),
		"provider":     callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), "different-provider-revision"),
		"command size": callMutation(t, adapter, runtimeport.OperationCommand, oversizedCommand, testBearerToken, context.Background(), testProviderRevisionID),
	} {
		t.Run(name, func(t *testing.T) {
			if outcome.Validate() != nil || outcome.Disposition() != runtimeport.MutationNotDispatched {
				t.Fatalf("outcome = %v", outcome)
			}
			failure, ok := outcome.Failure()
			if !ok || (failure.Class() != runtimeport.FailureInvalidRequest &&
				failure.Class() != runtimeport.FailureCanceled) {
				t.Fatalf("failure = %v", failure)
			}
		})
	}
	if requests.Load() != 0 {
		t.Fatalf("request count = %d", requests.Load())
	}
	if outcome := adapter.Start(context.Background(), runtimeport.StartRequest{}); outcome.Validate() == nil {
		t.Fatal("unconstructed zero request produced a valid mutation outcome")
	}
	if requests.Load() != 0 {
		t.Fatal("unconstructed zero request reached the network")
	}
	t.Log("http-adapter-evidence:sealed-pre-dispatch-zero-network:passed")
}

func TestMutationMapsOnlyDeclaredKnownRejections(t *testing.T) {
	for _, item := range []struct {
		operation runtimeport.Operation
		status    int
		class     runtimeport.FailureClass
	}{
		{runtimeport.OperationStart, http.StatusBadRequest, runtimeport.FailureInvalidRequest},
		{runtimeport.OperationStart, http.StatusUnauthorized, runtimeport.FailureAuthenticationRejected},
		{runtimeport.OperationStart, http.StatusForbidden, runtimeport.FailureAuthorityRejected},
		{runtimeport.OperationStart, http.StatusConflict, runtimeport.FailureProtocolConflict},
		{runtimeport.OperationStart, http.StatusRequestEntityTooLarge, runtimeport.FailurePayloadTooLarge},
		{runtimeport.OperationStart, http.StatusUnprocessableEntity, runtimeport.FailureUnsupported},
		{runtimeport.OperationStart, http.StatusTooManyRequests, runtimeport.FailureThrottled},
		{runtimeport.OperationCommand, http.StatusNotFound, runtimeport.FailureNotFound},
	} {
		name := string(item.operation) + "/" + strconv.Itoa(item.status)
		t.Run(name, func(t *testing.T) {
			adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writeAdapterJSON(writer, item.status, standardErrorDocument())
			}))
			body := adapterContractExample(t, "agent-runtime-start-request.json")
			if item.operation == runtimeport.OperationCommand {
				body = adapterContractExample(t, "agent-runtime-command.json")
			}
			outcome := callMutation(t, adapter, item.operation, body, testBearerToken, context.Background(), testProviderRevisionID)
			if outcome.Validate() != nil || outcome.Disposition() != runtimeport.MutationRejected {
				t.Fatalf("outcome = %v", outcome)
			}
			failure, ok := outcome.Failure()
			if !ok || failure.Class() != item.class || failure.Code() != "RUNTIME_TEST_ERROR" {
				t.Fatalf("failure = %v", failure)
			}
		})
	}
	t.Log("http-adapter-evidence:closed-known-mutation-rejections:passed")
}

func TestMutationUncertaintyRequiresFreshReadsAndNoRetry(t *testing.T) {
	startBody := adapterContractExample(t, "agent-runtime-start-request.json")
	for _, item := range []struct {
		name   string
		status int
		body   []byte
		class  runtimeport.FailureClass
	}{
		{"500", http.StatusInternalServerError, standardErrorDocument(), runtimeport.FailureInternal},
		{"503", http.StatusServiceUnavailable, standardErrorDocument(), runtimeport.FailureUnavailable},
		{"unexpected status", http.StatusTeapot, standardErrorDocument(), runtimeport.FailureInvalidResponse},
		{"invalid rejection body", http.StatusConflict, []byte(`{"invalid":true}`), runtimeport.FailureInvalidResponse},
	} {
		t.Run(item.name, func(t *testing.T) {
			var requests atomic.Int64
			adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				requests.Add(1)
				writeAdapterJSON(writer, item.status, item.body)
			}))
			outcome := callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), testProviderRevisionID)
			assertUnknownMutation(t, outcome, item.class)
			if requests.Load() != 1 {
				t.Fatalf("request count = %d", requests.Load())
			}
		})
	}
	t.Log("http-adapter-evidence:outcome-unknown-fresh-read-no-retry:passed")
}

func TestMutationResponseLossAndDeadlineDispatchOnlyOnce(t *testing.T) {
	startBody := adapterContractExample(t, "agent-runtime-start-request.json")
	t.Run("response loss", func(t *testing.T) {
		var requests atomic.Int64
		adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			requests.Add(1)
			_, _ = io.ReadAll(request.Body)
			connection, _, err := writer.(http.Hijacker).Hijack()
			if err != nil {
				t.Error(err)
				return
			}
			_ = connection.Close()
		}))
		outcome := callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), testProviderRevisionID)
		assertUnknownMutation(t, outcome, runtimeport.FailureTransport)
		if requests.Load() != 1 {
			t.Fatalf("request count = %d", requests.Load())
		}
	})

	t.Run("deadline", func(t *testing.T) {
		var requests atomic.Int64
		adapter := testTLSAdapterWithMutationTimeout(t, 50*time.Millisecond, http.HandlerFunc(func(_ http.ResponseWriter, request *http.Request) {
			requests.Add(1)
			select {
			case <-request.Context().Done():
			case <-time.After(500 * time.Millisecond):
			}
		}))
		outcome := callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), testProviderRevisionID)
		assertUnknownMutation(t, outcome, runtimeport.FailureDeadlineExceeded)
		if requests.Load() != 1 {
			t.Fatalf("request count = %d", requests.Load())
		}
	})
	t.Log("http-adapter-evidence:response-loss-deadline-single-dispatch:passed")
}

func TestMutationAcceptedResponseMustBindIdentityAndFencing(t *testing.T) {
	startBody := adapterContractExample(t, "agent-runtime-start-request.json")
	for name, mutate := range map[string]func(map[string]any){
		"runtime identity": func(document map[string]any) { document["runtime_run_id"] = "different-runtime-run" },
		"stale fencing":    func(document map[string]any) { document["observed_fencing_token"] = float64(0) },
	} {
		t.Run(name, func(t *testing.T) {
			status := mutateAdapterDocument(t, adapterContractExample(t, "agent-runtime-run-status.json"), mutate)
			adapter := testTLSAdapter(t, 1024*1024, http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writeAdapterJSON(writer, http.StatusAccepted, status)
			}))
			outcome := callMutation(t, adapter, runtimeport.OperationStart, startBody, testBearerToken, context.Background(), testProviderRevisionID)
			assertUnknownMutation(t, outcome, runtimeport.FailureInvalidResponse)
		})
	}
}

func callMutation(
	t *testing.T,
	adapter *Adapter,
	operation runtimeport.Operation,
	body []byte,
	tokenValue string,
	ctx context.Context,
	providerRevisionID string,
) runtimeport.MutationOutcome {
	t.Helper()
	invocation := mutationInvocation(t, operation, body, tokenValue, providerRevisionID)
	document, err := runtimeport.NewContractDocument(body, 8*1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	switch operation {
	case runtimeport.OperationStart:
		request, err := runtimeport.NewStartRequest(invocation, document)
		if err != nil {
			t.Fatal(err)
		}
		return adapter.Start(ctx, request)
	case runtimeport.OperationCommand:
		request, err := runtimeport.NewCommandRequest(invocation, document)
		if err != nil {
			t.Fatal(err)
		}
		return adapter.Command(ctx, request)
	default:
		t.Fatalf("unsupported operation %s", operation)
		return runtimeport.MutationOutcome{}
	}
}

func mutationInvocation(
	t *testing.T,
	operation runtimeport.Operation,
	body []byte,
	tokenValue string,
	providerRevisionID string,
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
	decoder := json.NewDecoder(bytes.NewReader(body))
	if err := decoder.Decode(&document); err != nil {
		t.Fatal(err)
	}
	digestValue := document.RequestDigest
	if operation == runtimeport.OperationCommand {
		digestValue = document.CommandDigest
	}
	digest, err := runtimeport.NewDigest(digestValue)
	if err != nil {
		t.Fatal(err)
	}
	token, err := runtimeport.NewInvocationToken([]byte(tokenValue), 16*1024)
	if err != nil {
		t.Fatal(err)
	}
	invocation, err := runtimeport.NewInvocation(
		operation,
		providerRevisionID,
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

func assertAcceptedMutation(t *testing.T, outcome runtimeport.MutationOutcome, operation runtimeport.Operation) {
	t.Helper()
	if outcome.Validate() != nil || outcome.Disposition() != runtimeport.MutationAccepted ||
		outcome.Reference().Operation() != operation {
		t.Fatalf("outcome = %v", outcome)
	}
	status, ok := outcome.AcceptedStatus()
	if !ok || status.RuntimeRunID() != testRuntimeRunID {
		t.Fatalf("accepted status = %v", status)
	}
}

func assertUnknownMutation(t *testing.T, outcome runtimeport.MutationOutcome, class runtimeport.FailureClass) {
	t.Helper()
	if outcome.Validate() != nil || outcome.Disposition() != runtimeport.MutationOutcomeUnknown {
		t.Fatalf("outcome = %v", outcome)
	}
	failure, ok := outcome.Failure()
	if !ok || failure.Class() != class {
		t.Fatalf("failure = %v", failure)
	}
	reconciliation, ok := outcome.Reconciliation()
	if !ok || !reconciliation.FreshReadAuthorityRequired() ||
		!reconciliation.OriginalMutationMustNotBeRetried() ||
		strings.Join(operationStrings(reconciliation.ReadOperations()), ",") != "read_status,read_events" {
		t.Fatalf("reconciliation = %v", reconciliation)
	}
}

func operationStrings(operations []runtimeport.Operation) []string {
	values := make([]string, len(operations))
	for index, operation := range operations {
		values[index] = string(operation)
	}
	return values
}

func testTLSAdapterWithMutationTimeout(t *testing.T, timeout time.Duration, handler http.Handler) *Adapter {
	t.Helper()
	bundle := testTLSServer(t, handler)
	configuration := testTLSConfiguration(t, bundle)
	configuration.ProviderRevisionID = testProviderRevisionID
	configuration.Validator = adapterContractValidator(t)
	configuration.Limits.MutationTimeout = timeout
	adapter, err := New(configuration)
	if err != nil {
		t.Fatal(err)
	}
	return adapter
}
