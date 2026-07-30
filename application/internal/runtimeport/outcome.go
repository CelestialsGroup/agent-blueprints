package runtimeport

import (
	"errors"
	"fmt"
)

var (
	ErrInvalidFailure                = errors.New("invalid runtime provider failure")
	ErrInvalidReadResult             = errors.New("invalid runtime provider read result")
	ErrInvalidMutationReference      = errors.New("invalid runtime provider mutation reference")
	ErrInvalidMutationDisposition    = errors.New("invalid runtime provider mutation disposition")
	ErrInvalidMutationOutcome        = errors.New("invalid runtime provider mutation outcome")
	ErrInvalidReconciliationRequired = errors.New("invalid runtime provider reconciliation requirement")
)

type FailureClass string

const (
	FailureInvalidRequest         FailureClass = "invalid_request"
	FailureAuthenticationRejected FailureClass = "authentication_rejected"
	FailureAuthorityRejected      FailureClass = "authority_rejected"
	FailureNotFound               FailureClass = "not_found"
	FailureProtocolConflict       FailureClass = "protocol_conflict"
	FailureCursorExpired          FailureClass = "cursor_expired"
	FailurePayloadTooLarge        FailureClass = "payload_too_large"
	FailureUnsupported            FailureClass = "unsupported"
	FailureThrottled              FailureClass = "throttled"
	FailureUnavailable            FailureClass = "unavailable"
	FailureInvalidResponse        FailureClass = "invalid_response"
	FailureDeadlineExceeded       FailureClass = "deadline_exceeded"
	FailureTransport              FailureClass = "transport_failure"
	FailureCanceled               FailureClass = "canceled"
	FailureInternal               FailureClass = "internal"
)

func (class FailureClass) Validate() error {
	switch class {
	case FailureInvalidRequest, FailureAuthenticationRejected, FailureAuthorityRejected,
		FailureNotFound, FailureProtocolConflict, FailureCursorExpired, FailurePayloadTooLarge,
		FailureUnsupported, FailureThrottled, FailureUnavailable, FailureInvalidResponse,
		FailureDeadlineExceeded, FailureTransport, FailureCanceled, FailureInternal:
		return nil
	default:
		return ErrInvalidFailure
	}
}

func (class FailureClass) isKnownMutationRejection() bool {
	switch class {
	case FailureInvalidRequest, FailureAuthenticationRejected, FailureAuthorityRejected,
		FailureNotFound, FailureProtocolConflict, FailurePayloadTooLarge, FailureUnsupported,
		FailureThrottled:
		return true
	default:
		return false
	}
}

func (class FailureClass) canBeNotDispatched() bool {
	switch class {
	case FailureInvalidRequest, FailureUnavailable, FailureDeadlineExceeded, FailureTransport,
		FailureCanceled, FailureInternal:
		return true
	default:
		return false
	}
}

func (class FailureClass) isMutationUncertainty() bool {
	switch class {
	case FailureUnavailable, FailureInvalidResponse, FailureDeadlineExceeded, FailureTransport,
		FailureCanceled, FailureInternal:
		return true
	default:
		return false
	}
}

// Failure retains only a closed class and bounded diagnostic code/details. It
// deliberately carries no raw transport error, response body, or retry policy.
type Failure struct {
	class   FailureClass
	code    string
	details *ContractDocument
}

func NewFailure(class FailureClass, code string, details *ContractDocument) (Failure, error) {
	failure := Failure{class: class, code: code}
	if details != nil {
		copied := copyDocument(*details)
		failure.details = &copied
	}
	if err := failure.Validate(); err != nil {
		return Failure{}, err
	}
	return failure, nil
}

func (failure Failure) Validate() error {
	if err := failure.class.Validate(); err != nil {
		return err
	}
	if !validDiagnosticCode(failure.code) {
		return ErrInvalidFailure
	}
	if failure.details != nil {
		if err := failure.details.Validate(); err != nil {
			return errors.Join(ErrInvalidFailure, err)
		}
	}
	return nil
}

func (failure Failure) Class() FailureClass { return failure.class }
func (failure Failure) Code() string        { return failure.code }

func (failure Failure) Details() (ContractDocument, bool) {
	if failure.details == nil {
		return ContractDocument{}, false
	}
	return copyDocument(*failure.details), true
}

func (failure Failure) String() string {
	return fmt.Sprintf("Failure{class=%s code=%s details=%s}", failure.class, failure.code, redactedValueString)
}

func (failure Failure) GoString() string {
	return failure.String()
}

// ReadResult is exactly one success value or one closed failure. Its zero value
// is invalid and cannot be mistaken for a successful read.
type ReadResult[T any] struct {
	value   *T
	failure *Failure
}

func NewReadSuccess[T any](value T) ReadResult[T] {
	return ReadResult[T]{value: &value}
}

func NewReadFailure[T any](failure Failure) (ReadResult[T], error) {
	if err := failure.Validate(); err != nil {
		return ReadResult[T]{}, errors.Join(ErrInvalidReadResult, err)
	}
	copied := copyFailure(failure)
	return ReadResult[T]{failure: &copied}, nil
}

func (result ReadResult[T]) Validate() error {
	if (result.value == nil) == (result.failure == nil) {
		return ErrInvalidReadResult
	}
	if result.failure != nil {
		if err := result.failure.Validate(); err != nil {
			return errors.Join(ErrInvalidReadResult, err)
		}
	}
	return nil
}

func (result ReadResult[T]) Succeeded() bool {
	return result.value != nil && result.failure == nil
}

func (result ReadResult[T]) Value() (T, bool) {
	if !result.Succeeded() {
		var zero T
		return zero, false
	}
	return *result.value, true
}

func (result ReadResult[T]) Failure() (Failure, bool) {
	if result.failure == nil || result.value != nil {
		return Failure{}, false
	}
	return copyFailure(*result.failure), true
}

func (result ReadResult[T]) String() string   { return "ReadResult" + redactedValueString }
func (result ReadResult[T]) GoString() string { return "ReadResult" + redactedValueString }

// MutationReference binds any mutation result to the single attempted request.
type MutationReference struct {
	operation           Operation
	providerRevisionID  string
	runtimeRunID        string
	invocationID        string
	invocationAttemptID string
	fencingToken        uint64
	requestDigest       Digest
}

func NewMutationReference(invocation Invocation) (MutationReference, error) {
	if err := invocation.Validate(); err != nil || !invocation.Operation().IsMutation() {
		return MutationReference{}, ErrInvalidMutationReference
	}
	return MutationReference{
		operation:           invocation.Operation(),
		providerRevisionID:  invocation.ProviderRevisionID(),
		runtimeRunID:        invocation.RuntimeRunID(),
		invocationID:        invocation.InvocationID(),
		invocationAttemptID: invocation.InvocationAttemptID(),
		fencingToken:        invocation.FencingToken(),
		requestDigest:       invocation.RequestDigest(),
	}, nil
}

func (reference MutationReference) Validate() error {
	if !reference.operation.IsMutation() {
		return ErrInvalidMutationReference
	}
	for _, item := range []struct {
		name  string
		value string
	}{
		{name: "provider_revision_id", value: reference.providerRevisionID},
		{name: "runtime_run_id", value: reference.runtimeRunID},
		{name: "invocation_id", value: reference.invocationID},
		{name: "invocation_attempt_id", value: reference.invocationAttemptID},
	} {
		if err := validateIdentifier(item.name, item.value); err != nil {
			return errors.Join(ErrInvalidMutationReference, err)
		}
	}
	if reference.fencingToken < 1 || reference.fencingToken > MaxSafeInteger {
		return errors.Join(ErrInvalidMutationReference, ErrInvalidFencingToken)
	}
	if err := reference.requestDigest.Validate(); err != nil {
		return errors.Join(ErrInvalidMutationReference, err)
	}
	return nil
}

func (reference MutationReference) Operation() Operation       { return reference.operation }
func (reference MutationReference) ProviderRevisionID() string { return reference.providerRevisionID }
func (reference MutationReference) RuntimeRunID() string       { return reference.runtimeRunID }
func (reference MutationReference) InvocationID() string       { return reference.invocationID }
func (reference MutationReference) InvocationAttemptID() string {
	return reference.invocationAttemptID
}
func (reference MutationReference) FencingToken() uint64  { return reference.fencingToken }
func (reference MutationReference) RequestDigest() Digest { return reference.requestDigest }
func (reference MutationReference) String() string        { return "MutationReference" + redactedValueString }
func (reference MutationReference) GoString() string {
	return "MutationReference" + redactedValueString
}

// ReconciliationRequirement records what a durable caller must do after an
// uncertain mutation. It does not obtain read authority or execute reconciliation.
type ReconciliationRequirement struct {
	reference      MutationReference
	readOperations []Operation
}

func NewReconciliationRequirement(
	reference MutationReference,
	readOperations []Operation,
) (ReconciliationRequirement, error) {
	requirement := ReconciliationRequirement{
		reference:      reference,
		readOperations: append([]Operation(nil), readOperations...),
	}
	if err := requirement.Validate(); err != nil {
		return ReconciliationRequirement{}, err
	}
	return requirement, nil
}

func (requirement ReconciliationRequirement) Validate() error {
	if err := requirement.reference.Validate(); err != nil {
		return errors.Join(ErrInvalidReconciliationRequired, err)
	}
	if len(requirement.readOperations) < 1 || len(requirement.readOperations) > 2 {
		return ErrInvalidReconciliationRequired
	}
	seen := make(map[Operation]struct{}, len(requirement.readOperations))
	for _, operation := range requirement.readOperations {
		if operation != OperationReadStatus && operation != OperationReadEvents {
			return ErrInvalidReconciliationRequired
		}
		if _, exists := seen[operation]; exists {
			return ErrInvalidReconciliationRequired
		}
		seen[operation] = struct{}{}
	}
	return nil
}

func (requirement ReconciliationRequirement) Reference() MutationReference {
	return requirement.reference
}

func (requirement ReconciliationRequirement) ReadOperations() []Operation {
	return append([]Operation(nil), requirement.readOperations...)
}

func (requirement ReconciliationRequirement) FreshReadAuthorityRequired() bool {
	return true
}

func (requirement ReconciliationRequirement) OriginalMutationMustNotBeRetried() bool {
	return true
}

func (requirement ReconciliationRequirement) String() string {
	return "ReconciliationRequirement" + redactedValueString
}

func (requirement ReconciliationRequirement) GoString() string {
	return "ReconciliationRequirement" + redactedValueString
}

type MutationDisposition string

const (
	MutationAccepted       MutationDisposition = "accepted"
	MutationRejected       MutationDisposition = "rejected"
	MutationNotDispatched  MutationDisposition = "not_dispatched"
	MutationOutcomeUnknown MutationDisposition = "outcome_unknown"
)

func (disposition MutationDisposition) Validate() error {
	switch disposition {
	case MutationAccepted, MutationRejected, MutationNotDispatched, MutationOutcomeUnknown:
		return nil
	default:
		return ErrInvalidMutationDisposition
	}
}

// MutationOutcome has four closed states. No state contains retry policy or an
// executor capable of issuing another mutation.
type MutationOutcome struct {
	disposition    MutationDisposition
	reference      MutationReference
	accepted       *RunStatus
	failure        *Failure
	reconciliation *ReconciliationRequirement
}

func NewAcceptedMutation(reference MutationReference, status RunStatus) (MutationOutcome, error) {
	outcome := MutationOutcome{disposition: MutationAccepted, reference: reference, accepted: &status}
	if err := outcome.Validate(); err != nil {
		return MutationOutcome{}, err
	}
	return outcome, nil
}

func NewRejectedMutation(reference MutationReference, failure Failure) (MutationOutcome, error) {
	copied := copyFailure(failure)
	outcome := MutationOutcome{disposition: MutationRejected, reference: reference, failure: &copied}
	if err := outcome.Validate(); err != nil {
		return MutationOutcome{}, err
	}
	return outcome, nil
}

func NewNotDispatchedMutation(reference MutationReference, failure Failure) (MutationOutcome, error) {
	copied := copyFailure(failure)
	outcome := MutationOutcome{disposition: MutationNotDispatched, reference: reference, failure: &copied}
	if err := outcome.Validate(); err != nil {
		return MutationOutcome{}, err
	}
	return outcome, nil
}

func NewUnknownMutation(
	reference MutationReference,
	failure Failure,
	reconciliation ReconciliationRequirement,
) (MutationOutcome, error) {
	copiedFailure := copyFailure(failure)
	copiedReconciliation := copyReconciliation(reconciliation)
	outcome := MutationOutcome{
		disposition:    MutationOutcomeUnknown,
		reference:      reference,
		failure:        &copiedFailure,
		reconciliation: &copiedReconciliation,
	}
	if err := outcome.Validate(); err != nil {
		return MutationOutcome{}, err
	}
	return outcome, nil
}

func (outcome MutationOutcome) Validate() error {
	if err := outcome.disposition.Validate(); err != nil {
		return errors.Join(ErrInvalidMutationOutcome, err)
	}
	if err := outcome.reference.Validate(); err != nil {
		return errors.Join(ErrInvalidMutationOutcome, err)
	}
	switch outcome.disposition {
	case MutationAccepted:
		if outcome.accepted == nil || outcome.failure != nil || outcome.reconciliation != nil {
			return ErrInvalidMutationOutcome
		}
		if outcome.accepted.RuntimeRunID() != outcome.reference.RuntimeRunID() ||
			outcome.accepted.ObservedFencingToken() < outcome.reference.FencingToken() {
			return ErrInvalidMutationOutcome
		}
	case MutationRejected:
		if outcome.accepted != nil || outcome.failure == nil || outcome.reconciliation != nil ||
			!outcome.failure.Class().isKnownMutationRejection() {
			return ErrInvalidMutationOutcome
		}
	case MutationNotDispatched:
		if outcome.accepted != nil || outcome.failure == nil || outcome.reconciliation != nil ||
			!outcome.failure.Class().canBeNotDispatched() {
			return ErrInvalidMutationOutcome
		}
	case MutationOutcomeUnknown:
		if outcome.accepted != nil || outcome.failure == nil || outcome.reconciliation == nil ||
			!outcome.failure.Class().isMutationUncertainty() {
			return ErrInvalidMutationOutcome
		}
		if err := outcome.reconciliation.Validate(); err != nil ||
			outcome.reconciliation.Reference() != outcome.reference {
			return ErrInvalidMutationOutcome
		}
	}
	if outcome.failure != nil {
		if err := outcome.failure.Validate(); err != nil {
			return errors.Join(ErrInvalidMutationOutcome, err)
		}
	}
	return nil
}

func (outcome MutationOutcome) Disposition() MutationDisposition { return outcome.disposition }
func (outcome MutationOutcome) Reference() MutationReference     { return outcome.reference }

func (outcome MutationOutcome) AcceptedStatus() (RunStatus, bool) {
	if outcome.accepted == nil || outcome.disposition != MutationAccepted {
		return RunStatus{}, false
	}
	return *outcome.accepted, true
}

func (outcome MutationOutcome) Failure() (Failure, bool) {
	if outcome.failure == nil || outcome.disposition == MutationAccepted {
		return Failure{}, false
	}
	return copyFailure(*outcome.failure), true
}

func (outcome MutationOutcome) Reconciliation() (ReconciliationRequirement, bool) {
	if outcome.reconciliation == nil || outcome.disposition != MutationOutcomeUnknown {
		return ReconciliationRequirement{}, false
	}
	return copyReconciliation(*outcome.reconciliation), true
}

func (outcome MutationOutcome) String() string   { return "MutationOutcome" + redactedValueString }
func (outcome MutationOutcome) GoString() string { return "MutationOutcome" + redactedValueString }

func validDiagnosticCode(code string) bool {
	if len(code) < 3 || len(code) > 128 || code[0] < 'A' || code[0] > 'Z' {
		return false
	}
	for _, character := range code[1:] {
		if (character < 'A' || character > 'Z') && (character < '0' || character > '9') && character != '_' {
			return false
		}
	}
	return true
}

func copyFailure(failure Failure) Failure {
	copied := Failure{class: failure.class, code: failure.code}
	if failure.details != nil {
		details := copyDocument(*failure.details)
		copied.details = &details
	}
	return copied
}

func copyReconciliation(requirement ReconciliationRequirement) ReconciliationRequirement {
	return ReconciliationRequirement{
		reference:      requirement.reference,
		readOperations: requirement.ReadOperations(),
	}
}
