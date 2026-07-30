package runtimeport

import (
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
)

func TestReadResultHasExactlyOneClosedState(t *testing.T) {
	status := testRunStatus(t, testRuntimeRunID, 4)
	success := NewReadSuccess(status)
	if err := success.Validate(); err != nil {
		t.Fatal(err)
	}
	value, ok := success.Value()
	if !ok || value.RuntimeRunID() != testRuntimeRunID {
		t.Fatal("read success value differs")
	}
	if _, ok := success.Failure(); ok {
		t.Fatal("read success contains failure")
	}
	failure := testFailure(t, FailureNotFound, "RUNTIME_RUN_NOT_FOUND", nil)
	failed, err := NewReadFailure[RunStatus](failure)
	if err != nil {
		t.Fatal(err)
	}
	if err := failed.Validate(); err != nil {
		t.Fatal(err)
	}
	if _, ok := failed.Value(); ok {
		t.Fatal("read failure contains success")
	}
	gotFailure, ok := failed.Failure()
	if !ok || gotFailure.Class() != FailureNotFound {
		t.Fatal("read failure differs")
	}
	if err := (ReadResult[RunStatus]{}).Validate(); !errors.Is(err, ErrInvalidReadResult) {
		t.Fatalf("zero read result error = %v", err)
	}
	mixed := ReadResult[RunStatus]{value: &status, failure: &failure}
	if err := mixed.Validate(); !errors.Is(err, ErrInvalidReadResult) {
		t.Fatalf("mixed read result error = %v", err)
	}
}

func TestMutationOutcomesCoverClosedDispositions(t *testing.T) {
	reference := testMutationReference(t, OperationStart)
	status := testRunStatus(t, reference.RuntimeRunID(), reference.FencingToken())
	rejectedFailure := testFailure(t, FailureProtocolConflict, "REQUEST_DIGEST_CONFLICT", nil)
	notDispatchedFailure := testFailure(t, FailureDeadlineExceeded, "DEADLINE_BEFORE_DISPATCH", nil)
	unknownFailure := testFailure(t, FailureTransport, "RESPONSE_LOST", nil)
	reconciliation := testReconciliation(t, reference)

	accepted, err := NewAcceptedMutation(reference, status)
	if err != nil {
		t.Fatal(err)
	}
	rejected, err := NewRejectedMutation(reference, rejectedFailure)
	if err != nil {
		t.Fatal(err)
	}
	notDispatched, err := NewNotDispatchedMutation(reference, notDispatchedFailure)
	if err != nil {
		t.Fatal(err)
	}
	unknown, err := NewUnknownMutation(reference, unknownFailure, reconciliation)
	if err != nil {
		t.Fatal(err)
	}

	for _, item := range []struct {
		outcome MutationOutcome
		want    MutationDisposition
	}{
		{outcome: accepted, want: MutationAccepted},
		{outcome: rejected, want: MutationRejected},
		{outcome: notDispatched, want: MutationNotDispatched},
		{outcome: unknown, want: MutationOutcomeUnknown},
	} {
		if err := item.outcome.Validate(); err != nil {
			t.Fatalf("validate %s: %v", item.want, err)
		}
		if item.outcome.Disposition() != item.want {
			t.Fatalf("disposition = %s, want %s", item.outcome.Disposition(), item.want)
		}
	}
	if acceptedStatus, ok := accepted.AcceptedStatus(); !ok || acceptedStatus.State() != RunStateAccepted {
		t.Fatal("accepted status is absent")
	}
	if failure, ok := rejected.Failure(); !ok || failure.Class() != FailureProtocolConflict {
		t.Fatal("known rejection failure differs")
	}
	if requirement, ok := unknown.Reconciliation(); !ok || !requirement.FreshReadAuthorityRequired() ||
		!requirement.OriginalMutationMustNotBeRetried() {
		t.Fatal("unknown outcome reconciliation boundary differs")
	}
}

func TestMutationOutcomeRejectsIllegalCombinations(t *testing.T) {
	reference := testMutationReference(t, OperationCommand)
	status := testRunStatus(t, reference.RuntimeRunID(), reference.FencingToken())
	rejectedFailure := testFailure(t, FailureProtocolConflict, "COMMAND_CONFLICT", nil)
	unknownFailure := testFailure(t, FailureUnavailable, "PROVIDER_UNAVAILABLE", nil)
	reconciliation := testReconciliation(t, reference)

	for name, outcome := range map[string]MutationOutcome{
		"zero": {},
		"accepted with failure": {
			disposition: MutationAccepted, reference: reference, accepted: &status, failure: &rejectedFailure,
		},
		"rejected with uncertain class": {
			disposition: MutationRejected, reference: reference, failure: &unknownFailure,
		},
		"unknown without reconciliation": {
			disposition: MutationOutcomeUnknown, reference: reference, failure: &unknownFailure,
		},
		"not dispatched with provider rejection": {
			disposition: MutationNotDispatched, reference: reference, failure: &rejectedFailure,
		},
	} {
		t.Run(name, func(t *testing.T) {
			if err := outcome.Validate(); !errors.Is(err, ErrInvalidMutationOutcome) {
				t.Fatalf("error = %v", err)
			}
		})
	}

	otherReference := testMutationReference(t, OperationStart)
	mismatchedRequirement := testReconciliation(t, otherReference)
	if _, err := NewUnknownMutation(reference, unknownFailure, mismatchedRequirement); !errors.Is(err, ErrInvalidMutationOutcome) {
		t.Fatalf("mismatched reconciliation error = %v", err)
	}
	mismatchedStatus := testRunStatus(t, "different-runtime-run", reference.FencingToken())
	if _, err := NewAcceptedMutation(reference, mismatchedStatus); !errors.Is(err, ErrInvalidMutationOutcome) {
		t.Fatalf("mismatched accepted status error = %v", err)
	}
	if _, err := NewUnknownMutation(reference, unknownFailure, reconciliation); err != nil {
		t.Fatalf("valid unknown outcome: %v", err)
	}
}

func TestReconciliationRequiresFreshBoundedReadOperations(t *testing.T) {
	reference := testMutationReference(t, OperationStart)
	operations := []Operation{OperationReadStatus, OperationReadEvents}
	requirement, err := NewReconciliationRequirement(reference, operations)
	if err != nil {
		t.Fatal(err)
	}
	operations[0] = OperationStart
	if requirement.ReadOperations()[0] != OperationReadStatus {
		t.Fatal("reconciliation aliases constructor operations")
	}
	copyOfOperations := requirement.ReadOperations()
	copyOfOperations[0] = OperationCommand
	if requirement.ReadOperations()[0] != OperationReadStatus {
		t.Fatal("reconciliation getter aliases operations")
	}
	for _, invalid := range [][]Operation{
		nil,
		{OperationReadStatus, OperationReadStatus},
		{OperationCommand},
		{OperationReadStatus, OperationReadEvents, OperationReadStatus},
	} {
		if _, err := NewReconciliationRequirement(reference, invalid); !errors.Is(err, ErrInvalidReconciliationRequired) {
			t.Fatalf("operations %v error = %v", invalid, err)
		}
	}
}

func TestFailureAndOutcomeRenderingRedactsDetails(t *testing.T) {
	details, err := NewContractDocument([]byte(`{"checkpoint":"checkpoint-content-canary"}`), 1024)
	if err != nil {
		t.Fatal(err)
	}
	failure := testFailure(t, FailureUnavailable, "PROVIDER_UNAVAILABLE", &details)
	reference := testMutationReference(t, OperationCommand)
	outcome, err := NewUnknownMutation(reference, failure, testReconciliation(t, reference))
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []any{failure, outcome, testReconciliation(t, reference)} {
		for _, rendered := range []string{fmt.Sprintf("%v", value), fmt.Sprintf("%+v", value), fmt.Sprintf("%#v", value)} {
			if strings.Contains(rendered, "checkpoint-content-canary") {
				t.Fatalf("diagnostic rendering leaked details: %s", rendered)
			}
		}
	}
	gotDetails, ok := failure.Details()
	if !ok {
		t.Fatal("failure details are absent")
	}
	mutated := gotDetails.Bytes()
	mutated[0] = 'X'
	gotAgain, _ := failure.Details()
	if gotAgain.Bytes()[0] != '{' {
		t.Fatal("failure details getter aliases internal bytes")
	}
}

func TestConcurrentOutcomeReadsRemainImmutable(t *testing.T) {
	reference := testMutationReference(t, OperationCommand)
	details := testDocument(t)
	failure := testFailure(t, FailureTransport, "RESPONSE_LOST", &details)
	outcome, err := NewUnknownMutation(reference, failure, testReconciliation(t, reference))
	if err != nil {
		t.Fatal(err)
	}
	var group sync.WaitGroup
	for range 32 {
		group.Add(1)
		go func() {
			defer group.Done()
			for range 100 {
				gotFailure, ok := outcome.Failure()
				if !ok || gotFailure.Code() != "RESPONSE_LOST" {
					t.Errorf("failure differs")
					return
				}
				gotDetails, ok := gotFailure.Details()
				if !ok {
					t.Errorf("details are absent")
					return
				}
				encoded := gotDetails.Bytes()
				encoded[0] = 'X'
				requirement, ok := outcome.Reconciliation()
				if !ok || len(requirement.ReadOperations()) != 2 {
					t.Errorf("reconciliation differs")
					return
				}
			}
		}()
	}
	group.Wait()
}

func FuzzMutationDispositionIsClosed(f *testing.F) {
	for _, seed := range []string{"", "accepted", "rejected", "not_dispatched", "outcome_unknown", "retry"} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, value string) {
		disposition := MutationDisposition(value)
		err := disposition.Validate()
		switch disposition {
		case MutationAccepted, MutationRejected, MutationNotDispatched, MutationOutcomeUnknown:
			if err != nil {
				t.Fatalf("closed disposition %q rejected: %v", disposition, err)
			}
		default:
			if !errors.Is(err, ErrInvalidMutationDisposition) {
				t.Fatalf("unknown disposition %q error = %v", disposition, err)
			}
		}
	})
}

func testMutationReference(t *testing.T, operation Operation) MutationReference {
	t.Helper()
	reference, err := NewMutationReference(testInvocation(t, operation))
	if err != nil {
		t.Fatal(err)
	}
	return reference
}

func testRunStatus(t *testing.T, runtimeRunID string, fencingToken uint64) RunStatus {
	t.Helper()
	status, err := NewRunStatus(runtimeRunID, RunStateAccepted, 0, 0, fencingToken, testDocument(t))
	if err != nil {
		t.Fatal(err)
	}
	return status
}

func testFailure(t *testing.T, class FailureClass, code string, details *ContractDocument) Failure {
	t.Helper()
	failure, err := NewFailure(class, code, details)
	if err != nil {
		t.Fatal(err)
	}
	return failure
}

func testReconciliation(t *testing.T, reference MutationReference) ReconciliationRequirement {
	t.Helper()
	requirement, err := NewReconciliationRequirement(
		reference,
		[]Operation{OperationReadStatus, OperationReadEvents},
	)
	if err != nil {
		t.Fatal(err)
	}
	return requirement
}
