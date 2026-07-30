package runtimeport

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestGoPortEvidenceMarkers(t *testing.T) {
	document := testDocument(t)
	token := testInvocation(t, OperationStart).Token()
	if document.Bytes()[0] != '{' || token.Len() == 0 || document.String() != redactedValueString ||
		token.String() != redactedValueString {
		t.Fatal("stable opaque value invariant differs")
	}
	t.Log("go-port-evidence:stable-values-copy-redaction:passed")

	read := NewReadSuccess(testRunStatus(t, testRuntimeRunID, 4))
	if err := read.Validate(); err != nil || !read.Succeeded() {
		t.Fatalf("read result invariant differs: %v", err)
	}
	t.Log("go-port-evidence:closed-read-result:passed")

	reference := testMutationReference(t, OperationCommand)
	status := testRunStatus(t, reference.RuntimeRunID(), reference.FencingToken())
	rejected := testFailure(t, FailureProtocolConflict, "COMMAND_CONFLICT", nil)
	notDispatched := testFailure(t, FailureDeadlineExceeded, "DEADLINE_BEFORE_DISPATCH", nil)
	unknown := testFailure(t, FailureTransport, "RESPONSE_LOST", nil)
	requirement := testReconciliation(t, reference)
	results := make([]MutationOutcome, 0, 4)
	acceptedResult, err := NewAcceptedMutation(reference, status)
	if err != nil {
		t.Fatal(err)
	}
	results = append(results, acceptedResult)
	rejectedResult, err := NewRejectedMutation(reference, rejected)
	if err != nil {
		t.Fatal(err)
	}
	results = append(results, rejectedResult)
	notDispatchedResult, err := NewNotDispatchedMutation(reference, notDispatched)
	if err != nil {
		t.Fatal(err)
	}
	results = append(results, notDispatchedResult)
	unknownResult, err := NewUnknownMutation(reference, unknown, requirement)
	if err != nil {
		t.Fatal(err)
	}
	results = append(results, unknownResult)
	for index, disposition := range []MutationDisposition{
		MutationAccepted,
		MutationRejected,
		MutationNotDispatched,
		MutationOutcomeUnknown,
	} {
		if results[index].Disposition() != disposition || results[index].Validate() != nil {
			t.Fatalf("mutation disposition %s differs", disposition)
		}
	}
	t.Log("go-port-evidence:four-mutation-dispositions:passed")

	gotRequirement, ok := unknownResult.Reconciliation()
	if !ok || !gotRequirement.FreshReadAuthorityRequired() ||
		!gotRequirement.OriginalMutationMustNotBeRetried() || len(gotRequirement.ReadOperations()) != 2 {
		t.Fatal("reconciliation requirement differs")
	}
	t.Log("go-port-evidence:fresh-read-reconciliation-no-retry:passed")

	mixed := MutationOutcome{
		disposition: MutationAccepted,
		reference:   reference,
		accepted:    &status,
		failure:     &rejected,
	}
	if mixed.Validate() == nil || (MutationOutcome{}).Validate() == nil {
		t.Fatal("illegal mutation state was accepted")
	}
	t.Log("go-port-evidence:illegal-outcome-states-rejected:passed")

	portType := reflect.TypeOf((*AgentRuntimeProvider)(nil)).Elem()
	wantMethods := []string{"Capabilities", "Command", "Events", "Start", "Status"}
	if portType.NumMethod() != len(wantMethods) {
		t.Fatalf("Port method count = %d", portType.NumMethod())
	}
	for index, want := range wantMethods {
		method := portType.Method(index)
		if method.Name != want || strings.Contains(strings.ToLower(method.Name), "retry") {
			t.Fatalf("Port method %d = %s", index, method.Name)
		}
	}
	for _, valueType := range []reflect.Type{
		reflect.TypeOf(MutationOutcome{}),
		reflect.TypeOf(ReconciliationRequirement{}),
	} {
		for index := range valueType.NumMethod() {
			if strings.Contains(strings.ToLower(valueType.Method(index).Name), "retry") {
				t.Fatalf("retry-capable method leaked: %s", valueType.Method(index).Name)
			}
		}
	}
	var _ AgentRuntimeProvider = compileTimeProvider{}
	var _ context.Context = context.Background()
	t.Log("go-port-evidence:five-operation-port-no-retry-surface:passed")
}
