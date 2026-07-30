package runtimeport

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
)

const (
	testProviderRevisionID = "provider-revision-1"
	testRuntimeRunID       = "runtime-run-1"
	testInvocationID       = "invocation-1"
	testAttemptID          = "attempt-1"
	testDigest             = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)

type compileTimeProvider struct{}

func (compileTimeProvider) Capabilities(context.Context, CapabilitiesRequest) ReadResult[ProviderCapabilities] {
	return ReadResult[ProviderCapabilities]{}
}

func (compileTimeProvider) Start(context.Context, StartRequest) MutationOutcome {
	return MutationOutcome{}
}

func (compileTimeProvider) Status(context.Context, StatusRequest) ReadResult[RunStatus] {
	return ReadResult[RunStatus]{}
}

func (compileTimeProvider) Command(context.Context, CommandRequest) MutationOutcome {
	return MutationOutcome{}
}

func (compileTimeProvider) Events(context.Context, EventsRequest) ReadResult[EventPage] {
	return ReadResult[EventPage]{}
}

var _ AgentRuntimeProvider = compileTimeProvider{}

func TestOperationSetIsClosed(t *testing.T) {
	for _, operation := range []Operation{
		OperationCapabilities,
		OperationStart,
		OperationReadStatus,
		OperationCommand,
		OperationReadEvents,
	} {
		if err := operation.Validate(); err != nil {
			t.Fatalf("validate %q: %v", operation, err)
		}
	}
	if err := Operation("http_post").Validate(); !errors.Is(err, ErrInvalidOperation) {
		t.Fatalf("unknown operation error = %v", err)
	}
	if !OperationStart.IsMutation() || !OperationCommand.IsMutation() || OperationReadStatus.IsMutation() {
		t.Fatal("mutation classification differs")
	}
	if !OperationCapabilities.IsRead() || !OperationReadStatus.IsRead() || !OperationReadEvents.IsRead() {
		t.Fatal("read classification differs")
	}
}

func TestOpaqueValuesCopyAndRedact(t *testing.T) {
	tokenSource := []byte("header.payload.signature-token-canary")
	documentSource := []byte(`{"input":"request-body-canary"}`)
	token, err := NewInvocationToken(tokenSource, len(tokenSource))
	if err != nil {
		t.Fatal(err)
	}
	document, err := NewContractDocument(documentSource, len(documentSource))
	if err != nil {
		t.Fatal(err)
	}
	tokenSource[0] = 'X'
	documentSource[0] = 'X'
	if string(token.Bytes()) != "header.payload.signature-token-canary" {
		t.Fatal("token aliases constructor input")
	}
	if string(document.Bytes()) != `{"input":"request-body-canary"}` {
		t.Fatal("document aliases constructor input")
	}
	tokenCopy := token.Bytes()
	documentCopy := document.Bytes()
	tokenCopy[0] = 'Y'
	documentCopy[0] = 'Y'
	if token.Bytes()[0] != 'h' || document.Bytes()[0] != '{' {
		t.Fatal("opaque getter exposes mutable storage")
	}
	for _, rendered := range []string{
		fmt.Sprintf("%v", token),
		fmt.Sprintf("%+v", token),
		fmt.Sprintf("%#v", token),
		fmt.Sprintf("%v", document),
		fmt.Sprintf("%#v", document),
	} {
		if strings.Contains(rendered, "token-canary") || strings.Contains(rendered, "request-body-canary") {
			t.Fatalf("opaque value leaked: %s", rendered)
		}
	}
}

func TestInvocationAndRequestOperationBindings(t *testing.T) {
	startInvocation := testInvocation(t, OperationStart)
	document := testDocument(t)
	start, err := NewStartRequest(startInvocation, document)
	if err != nil {
		t.Fatal(err)
	}
	if start.Invocation().Operation() != OperationStart {
		t.Fatal("start operation differs")
	}
	if _, err := NewCommandRequest(startInvocation, document); !errors.Is(err, ErrInvalidOperation) {
		t.Fatalf("mismatched command error = %v", err)
	}
	statusInvocation := testInvocation(t, OperationReadStatus)
	if _, err := NewStatusRequest(statusInvocation); err != nil {
		t.Fatal(err)
	}
	if _, err := NewStartRequest(statusInvocation, document); !errors.Is(err, ErrInvalidOperation) {
		t.Fatalf("mismatched start error = %v", err)
	}
	eventsInvocation := testInvocation(t, OperationReadEvents)
	events, err := NewEventsRequest(eventsInvocation, MaxSafeInteger, MaxEventReadLimit)
	if err != nil {
		t.Fatal(err)
	}
	if events.AfterEventSequence() != MaxSafeInteger || events.Limit() != MaxEventReadLimit {
		t.Fatal("event request values differ")
	}
	if _, err := NewEventsRequest(eventsInvocation, MaxSafeInteger+1, 1); !errors.Is(err, ErrInvalidSequence) {
		t.Fatalf("event cursor error = %v", err)
	}
	if _, err := NewEventsRequest(eventsInvocation, 0, 0); !errors.Is(err, ErrInvalidEventReadLimit) {
		t.Fatalf("event limit error = %v", err)
	}
}

func TestStableResponseValuesCopyDocuments(t *testing.T) {
	document := testDocument(t)
	capabilities, err := NewProviderCapabilities(testProviderRevisionID, document)
	if err != nil {
		t.Fatal(err)
	}
	status, err := NewRunStatus(testRuntimeRunID, RunStateCancelRequested, 2, 3, 4, document)
	if err != nil {
		t.Fatal(err)
	}
	page, err := NewEventPage(testRuntimeRunID, 3, document)
	if err != nil {
		t.Fatal(err)
	}
	for _, got := range [][]byte{
		capabilities.Document().Bytes(),
		status.Document().Bytes(),
		page.Document().Bytes(),
	} {
		got[0] = 'X'
	}
	if capabilities.Document().Bytes()[0] != '{' || status.Document().Bytes()[0] != '{' || page.Document().Bytes()[0] != '{' {
		t.Fatal("response document getter aliases internal bytes")
	}
	if status.State() != RunStateCancelRequested {
		t.Fatal("cancel acceptance state differs")
	}
	if _, err := NewRunStatus(testRuntimeRunID, RunState("terminal_cancel_requested"), 0, 0, 1, document); !errors.Is(err, ErrInvalidResponseValue) {
		t.Fatalf("unknown run state error = %v", err)
	}
}

func TestConstructorsRejectUnboundedOrInvalidValues(t *testing.T) {
	if _, err := NewInvocationToken([]byte("token"), 0); !errors.Is(err, ErrInvalidInvocationToken) {
		t.Fatalf("unbounded token error = %v", err)
	}
	if _, err := NewContractDocument([]byte("{}"), 0); !errors.Is(err, ErrInvalidDocument) {
		t.Fatalf("unbounded document error = %v", err)
	}
	if _, err := NewContractDocument([]byte{0xff}, 1); !errors.Is(err, ErrInvalidDocument) {
		t.Fatalf("invalid UTF-8 document error = %v", err)
	}
	if _, err := NewCapabilitiesRequest(""); !errors.Is(err, ErrInvalidIdentifier) {
		t.Fatalf("empty provider revision error = %v", err)
	}
	digest, err := NewDigest(testDigest)
	if err != nil {
		t.Fatal(err)
	}
	token, err := NewInvocationToken([]byte("token"), 5)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewInvocation(OperationCapabilities, testProviderRevisionID, testRuntimeRunID, testInvocationID, testAttemptID, 1, digest, token); !errors.Is(err, ErrInvalidOperation) {
		t.Fatalf("capabilities invocation error = %v", err)
	}
	if _, err := NewInvocation(OperationStart, testProviderRevisionID, testRuntimeRunID, testInvocationID, testAttemptID, MaxSafeInteger+1, digest, token); !errors.Is(err, ErrInvalidFencingToken) {
		t.Fatalf("oversized fencing token error = %v", err)
	}
}

func testInvocation(t *testing.T, operation Operation) Invocation {
	t.Helper()
	digest, err := NewDigest(testDigest)
	if err != nil {
		t.Fatal(err)
	}
	token, err := NewInvocationToken([]byte("header.payload.signature-token-canary"), 128)
	if err != nil {
		t.Fatal(err)
	}
	invocation, err := NewInvocation(
		operation,
		testProviderRevisionID,
		testRuntimeRunID,
		testInvocationID,
		testAttemptID,
		4,
		digest,
		token,
	)
	if err != nil {
		t.Fatal(err)
	}
	return invocation
}

func testDocument(t *testing.T) ContractDocument {
	t.Helper()
	document, err := NewContractDocument([]byte(`{"status":"accepted"}`), 1024)
	if err != nil {
		t.Fatal(err)
	}
	return document
}
