package runtimeport

import (
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"
)

const (
	MaxIdentifierBytes  = 200
	MaxSafeInteger      = uint64(1<<53 - 1)
	MaxEventReadLimit   = uint32(1000)
	redactedValueString = "[REDACTED]"
)

var (
	ErrInvalidOperation       = errors.New("invalid runtime provider operation")
	ErrInvalidIdentifier      = errors.New("invalid runtime provider identifier")
	ErrInvalidDigest          = errors.New("invalid runtime provider digest")
	ErrInvalidFencingToken    = errors.New("invalid runtime provider fencing token")
	ErrInvalidSequence        = errors.New("invalid runtime provider sequence")
	ErrInvalidEventReadLimit  = errors.New("invalid runtime provider event read limit")
	ErrInvalidInvocationToken = errors.New("invalid runtime provider invocation token")
	ErrInvalidDocument        = errors.New("invalid runtime provider contract document")
	ErrInvalidInvocation      = errors.New("invalid runtime provider invocation")
	ErrInvalidRequest         = errors.New("invalid runtime provider request")
	ErrInvalidResponseValue   = errors.New("invalid runtime provider response value")
)

// Operation is the stable Port operation name, independent of HTTP operation IDs.
type Operation string

const (
	OperationCapabilities Operation = "capabilities"
	OperationStart        Operation = "start"
	OperationReadStatus   Operation = "read_status"
	OperationCommand      Operation = "submit_command"
	OperationReadEvents   Operation = "read_events"
)

func (operation Operation) Validate() error {
	switch operation {
	case OperationCapabilities, OperationStart, OperationReadStatus, OperationCommand, OperationReadEvents:
		return nil
	default:
		return ErrInvalidOperation
	}
}

func (operation Operation) IsMutation() bool {
	return operation == OperationStart || operation == OperationCommand
}

func (operation Operation) IsRead() bool {
	return operation == OperationCapabilities || operation == OperationReadStatus || operation == OperationReadEvents
}

// Digest is a lower-case sha256 URI used as a stable request identity.
type Digest string

func NewDigest(value string) (Digest, error) {
	if len(value) != len("sha256:")+64 || !strings.HasPrefix(value, "sha256:") {
		return "", ErrInvalidDigest
	}
	for _, character := range value[len("sha256:"):] {
		if (character < '0' || character > '9') && (character < 'a' || character > 'f') {
			return "", ErrInvalidDigest
		}
	}
	return Digest(value), nil
}

func (digest Digest) Validate() error {
	_, err := NewDigest(string(digest))
	return err
}

// InvocationToken is opaque to the Port. Construction proves only an explicit byte bound.
type InvocationToken struct {
	encoded []byte
}

func NewInvocationToken(encoded []byte, maxBytes int) (InvocationToken, error) {
	if maxBytes < 1 || len(encoded) == 0 || len(encoded) > maxBytes {
		return InvocationToken{}, ErrInvalidInvocationToken
	}
	return InvocationToken{encoded: append([]byte(nil), encoded...)}, nil
}

func (token InvocationToken) Bytes() []byte {
	return append([]byte(nil), token.encoded...)
}

func (token InvocationToken) Len() int {
	return len(token.encoded)
}

func (token InvocationToken) Validate() error {
	if len(token.encoded) == 0 {
		return ErrInvalidInvocationToken
	}
	return nil
}

func (token InvocationToken) String() string {
	return redactedValueString
}

func (token InvocationToken) GoString() string {
	return redactedValueString
}

// ContractDocument is an immutable opaque transport document. It does not claim JSON,
// Schema, semantic, digest, or signature validation.
type ContractDocument struct {
	encoded []byte
}

func NewContractDocument(encoded []byte, maxBytes int) (ContractDocument, error) {
	if maxBytes < 1 || len(encoded) == 0 || len(encoded) > maxBytes || !utf8.Valid(encoded) {
		return ContractDocument{}, ErrInvalidDocument
	}
	return ContractDocument{encoded: append([]byte(nil), encoded...)}, nil
}

func (document ContractDocument) Bytes() []byte {
	return append([]byte(nil), document.encoded...)
}

func (document ContractDocument) Len() int {
	return len(document.encoded)
}

func (document ContractDocument) Validate() error {
	if len(document.encoded) == 0 || !utf8.Valid(document.encoded) {
		return ErrInvalidDocument
	}
	return nil
}

func (document ContractDocument) String() string {
	return redactedValueString
}

func (document ContractDocument) GoString() string {
	return redactedValueString
}

// Invocation identifies one already-authorized Provider operation. It does not issue
// or validate the opaque token and carries no endpoint or TLS authority.
type Invocation struct {
	operation           Operation
	providerRevisionID  string
	runtimeRunID        string
	invocationID        string
	invocationAttemptID string
	fencingToken        uint64
	requestDigest       Digest
	token               InvocationToken
}

func NewInvocation(
	operation Operation,
	providerRevisionID string,
	runtimeRunID string,
	invocationID string,
	invocationAttemptID string,
	fencingToken uint64,
	requestDigest Digest,
	token InvocationToken,
) (Invocation, error) {
	invocation := Invocation{
		operation:           operation,
		providerRevisionID:  providerRevisionID,
		runtimeRunID:        runtimeRunID,
		invocationID:        invocationID,
		invocationAttemptID: invocationAttemptID,
		fencingToken:        fencingToken,
		requestDigest:       requestDigest,
		token:               token,
	}
	if err := invocation.Validate(); err != nil {
		return Invocation{}, err
	}
	return invocation, nil
}

func (invocation Invocation) Validate() error {
	if err := invocation.operation.Validate(); err != nil || invocation.operation == OperationCapabilities {
		return errors.Join(ErrInvalidInvocation, ErrInvalidOperation)
	}
	for _, item := range []struct {
		name  string
		value string
	}{
		{name: "provider_revision_id", value: invocation.providerRevisionID},
		{name: "runtime_run_id", value: invocation.runtimeRunID},
		{name: "invocation_id", value: invocation.invocationID},
		{name: "invocation_attempt_id", value: invocation.invocationAttemptID},
	} {
		if err := validateIdentifier(item.name, item.value); err != nil {
			return errors.Join(ErrInvalidInvocation, err)
		}
	}
	if invocation.fencingToken < 1 || invocation.fencingToken > MaxSafeInteger {
		return errors.Join(ErrInvalidInvocation, ErrInvalidFencingToken)
	}
	if err := invocation.requestDigest.Validate(); err != nil {
		return errors.Join(ErrInvalidInvocation, err)
	}
	if err := invocation.token.Validate(); err != nil {
		return errors.Join(ErrInvalidInvocation, err)
	}
	return nil
}

func (invocation Invocation) Operation() Operation        { return invocation.operation }
func (invocation Invocation) ProviderRevisionID() string  { return invocation.providerRevisionID }
func (invocation Invocation) RuntimeRunID() string        { return invocation.runtimeRunID }
func (invocation Invocation) InvocationID() string        { return invocation.invocationID }
func (invocation Invocation) InvocationAttemptID() string { return invocation.invocationAttemptID }
func (invocation Invocation) FencingToken() uint64        { return invocation.fencingToken }
func (invocation Invocation) RequestDigest() Digest       { return invocation.requestDigest }
func (invocation Invocation) Token() InvocationToken {
	return InvocationToken{encoded: invocation.token.Bytes()}
}
func (invocation Invocation) String() string   { return "Invocation" + redactedValueString }
func (invocation Invocation) GoString() string { return "Invocation" + redactedValueString }

type CapabilitiesRequest struct {
	expectedProviderRevisionID string
}

func NewCapabilitiesRequest(expectedProviderRevisionID string) (CapabilitiesRequest, error) {
	if err := validateIdentifier("expected_provider_revision_id", expectedProviderRevisionID); err != nil {
		return CapabilitiesRequest{}, errors.Join(ErrInvalidRequest, err)
	}
	return CapabilitiesRequest{expectedProviderRevisionID: expectedProviderRevisionID}, nil
}

func (request CapabilitiesRequest) ExpectedProviderRevisionID() string {
	return request.expectedProviderRevisionID
}

func (request CapabilitiesRequest) Validate() error {
	if err := validateIdentifier("expected_provider_revision_id", request.expectedProviderRevisionID); err != nil {
		return errors.Join(ErrInvalidRequest, err)
	}
	return nil
}

type StartRequest struct {
	invocation Invocation
	document   ContractDocument
}

func NewStartRequest(invocation Invocation, document ContractDocument) (StartRequest, error) {
	request := StartRequest{invocation: invocation, document: document}
	if err := request.Validate(); err != nil {
		return StartRequest{}, err
	}
	return request, nil
}

func (request StartRequest) Validate() error {
	return validateMutationRequest(OperationStart, request.invocation, request.document)
}

func (request StartRequest) Invocation() Invocation     { return request.invocation }
func (request StartRequest) Document() ContractDocument { return copyDocument(request.document) }
func (request StartRequest) String() string             { return "StartRequest" + redactedValueString }
func (request StartRequest) GoString() string           { return "StartRequest" + redactedValueString }

type CommandRequest struct {
	invocation Invocation
	document   ContractDocument
}

func NewCommandRequest(invocation Invocation, document ContractDocument) (CommandRequest, error) {
	request := CommandRequest{invocation: invocation, document: document}
	if err := request.Validate(); err != nil {
		return CommandRequest{}, err
	}
	return request, nil
}

func (request CommandRequest) Validate() error {
	return validateMutationRequest(OperationCommand, request.invocation, request.document)
}

func (request CommandRequest) Invocation() Invocation     { return request.invocation }
func (request CommandRequest) Document() ContractDocument { return copyDocument(request.document) }
func (request CommandRequest) String() string             { return "CommandRequest" + redactedValueString }
func (request CommandRequest) GoString() string           { return "CommandRequest" + redactedValueString }

type StatusRequest struct {
	invocation Invocation
}

func NewStatusRequest(invocation Invocation) (StatusRequest, error) {
	request := StatusRequest{invocation: invocation}
	if err := request.Validate(); err != nil {
		return StatusRequest{}, err
	}
	return request, nil
}

func (request StatusRequest) Validate() error {
	return validateReadRequest(OperationReadStatus, request.invocation)
}

func (request StatusRequest) Invocation() Invocation { return request.invocation }
func (request StatusRequest) String() string         { return "StatusRequest" + redactedValueString }
func (request StatusRequest) GoString() string       { return "StatusRequest" + redactedValueString }

type EventsRequest struct {
	invocation         Invocation
	afterEventSequence uint64
	limit              uint32
}

func NewEventsRequest(invocation Invocation, afterEventSequence uint64, limit uint32) (EventsRequest, error) {
	request := EventsRequest{
		invocation:         invocation,
		afterEventSequence: afterEventSequence,
		limit:              limit,
	}
	if err := request.Validate(); err != nil {
		return EventsRequest{}, err
	}
	return request, nil
}

func (request EventsRequest) Validate() error {
	if err := validateReadRequest(OperationReadEvents, request.invocation); err != nil {
		return err
	}
	if request.afterEventSequence > MaxSafeInteger {
		return errors.Join(ErrInvalidRequest, ErrInvalidSequence)
	}
	if request.limit < 1 || request.limit > MaxEventReadLimit {
		return errors.Join(ErrInvalidRequest, ErrInvalidEventReadLimit)
	}
	return nil
}

func (request EventsRequest) Invocation() Invocation     { return request.invocation }
func (request EventsRequest) AfterEventSequence() uint64 { return request.afterEventSequence }
func (request EventsRequest) Limit() uint32              { return request.limit }
func (request EventsRequest) String() string             { return "EventsRequest" + redactedValueString }
func (request EventsRequest) GoString() string           { return "EventsRequest" + redactedValueString }

type ProviderCapabilities struct {
	providerRevisionID string
	document           ContractDocument
}

func NewProviderCapabilities(providerRevisionID string, document ContractDocument) (ProviderCapabilities, error) {
	if err := validateIdentifier("provider_revision_id", providerRevisionID); err != nil {
		return ProviderCapabilities{}, errors.Join(ErrInvalidResponseValue, err)
	}
	if err := document.Validate(); err != nil {
		return ProviderCapabilities{}, errors.Join(ErrInvalidResponseValue, err)
	}
	return ProviderCapabilities{providerRevisionID: providerRevisionID, document: copyDocument(document)}, nil
}

func (value ProviderCapabilities) ProviderRevisionID() string { return value.providerRevisionID }
func (value ProviderCapabilities) Document() ContractDocument { return copyDocument(value.document) }
func (value ProviderCapabilities) String() string {
	return "ProviderCapabilities" + redactedValueString
}
func (value ProviderCapabilities) GoString() string {
	return "ProviderCapabilities" + redactedValueString
}

type RunState string

const (
	RunStateAccepted        RunState = "accepted"
	RunStateRunning         RunState = "running"
	RunStateWaitingInput    RunState = "waiting_input"
	RunStateWaitingApproval RunState = "waiting_approval"
	RunStatePaused          RunState = "paused"
	RunStateCancelRequested RunState = "cancel_requested"
	RunStateSucceeded       RunState = "succeeded"
	RunStateFailed          RunState = "failed"
	RunStateCancelled       RunState = "cancelled"
	RunStateOutcomeUnknown  RunState = "outcome_unknown"
)

func (state RunState) Validate() error {
	switch state {
	case RunStateAccepted, RunStateRunning, RunStateWaitingInput, RunStateWaitingApproval,
		RunStatePaused, RunStateCancelRequested, RunStateSucceeded, RunStateFailed,
		RunStateCancelled, RunStateOutcomeUnknown:
		return nil
	default:
		return ErrInvalidResponseValue
	}
}

type RunStatus struct {
	runtimeRunID         string
	state                RunState
	lastCommandSequence  uint64
	lastEventSequence    uint64
	observedFencingToken uint64
	document             ContractDocument
}

func NewRunStatus(
	runtimeRunID string,
	state RunState,
	lastCommandSequence uint64,
	lastEventSequence uint64,
	observedFencingToken uint64,
	document ContractDocument,
) (RunStatus, error) {
	if err := validateIdentifier("runtime_run_id", runtimeRunID); err != nil {
		return RunStatus{}, errors.Join(ErrInvalidResponseValue, err)
	}
	if err := state.Validate(); err != nil {
		return RunStatus{}, err
	}
	if lastCommandSequence > MaxSafeInteger || lastEventSequence > MaxSafeInteger {
		return RunStatus{}, errors.Join(ErrInvalidResponseValue, ErrInvalidSequence)
	}
	if observedFencingToken < 1 || observedFencingToken > MaxSafeInteger {
		return RunStatus{}, errors.Join(ErrInvalidResponseValue, ErrInvalidFencingToken)
	}
	if err := document.Validate(); err != nil {
		return RunStatus{}, errors.Join(ErrInvalidResponseValue, err)
	}
	return RunStatus{
		runtimeRunID:         runtimeRunID,
		state:                state,
		lastCommandSequence:  lastCommandSequence,
		lastEventSequence:    lastEventSequence,
		observedFencingToken: observedFencingToken,
		document:             copyDocument(document),
	}, nil
}

func (status RunStatus) RuntimeRunID() string         { return status.runtimeRunID }
func (status RunStatus) State() RunState              { return status.state }
func (status RunStatus) LastCommandSequence() uint64  { return status.lastCommandSequence }
func (status RunStatus) LastEventSequence() uint64    { return status.lastEventSequence }
func (status RunStatus) ObservedFencingToken() uint64 { return status.observedFencingToken }
func (status RunStatus) Document() ContractDocument   { return copyDocument(status.document) }
func (status RunStatus) String() string               { return "RunStatus" + redactedValueString }
func (status RunStatus) GoString() string             { return "RunStatus" + redactedValueString }

type EventPage struct {
	runtimeRunID      string
	nextEventSequence uint64
	document          ContractDocument
}

func NewEventPage(runtimeRunID string, nextEventSequence uint64, document ContractDocument) (EventPage, error) {
	if err := validateIdentifier("runtime_run_id", runtimeRunID); err != nil {
		return EventPage{}, errors.Join(ErrInvalidResponseValue, err)
	}
	if nextEventSequence > MaxSafeInteger {
		return EventPage{}, errors.Join(ErrInvalidResponseValue, ErrInvalidSequence)
	}
	if err := document.Validate(); err != nil {
		return EventPage{}, errors.Join(ErrInvalidResponseValue, err)
	}
	return EventPage{
		runtimeRunID:      runtimeRunID,
		nextEventSequence: nextEventSequence,
		document:          copyDocument(document),
	}, nil
}

func (page EventPage) RuntimeRunID() string       { return page.runtimeRunID }
func (page EventPage) NextEventSequence() uint64  { return page.nextEventSequence }
func (page EventPage) Document() ContractDocument { return copyDocument(page.document) }
func (page EventPage) String() string             { return "EventPage" + redactedValueString }
func (page EventPage) GoString() string           { return "EventPage" + redactedValueString }

func validateMutationRequest(expected Operation, invocation Invocation, document ContractDocument) error {
	if err := invocation.Validate(); err != nil {
		return errors.Join(ErrInvalidRequest, err)
	}
	if invocation.Operation() != expected || !expected.IsMutation() {
		return errors.Join(ErrInvalidRequest, ErrInvalidOperation)
	}
	if err := document.Validate(); err != nil {
		return errors.Join(ErrInvalidRequest, err)
	}
	return nil
}

func validateReadRequest(expected Operation, invocation Invocation) error {
	if err := invocation.Validate(); err != nil {
		return errors.Join(ErrInvalidRequest, err)
	}
	if invocation.Operation() != expected || !expected.IsRead() || expected == OperationCapabilities {
		return errors.Join(ErrInvalidRequest, ErrInvalidOperation)
	}
	return nil
}

func validateIdentifier(name string, value string) error {
	if value == "" || len(value) > MaxIdentifierBytes || !utf8.ValidString(value) || strings.IndexByte(value, 0) >= 0 {
		return fmt.Errorf("%w: %s must be valid UTF-8 without NUL and contain 1-%d bytes", ErrInvalidIdentifier, name, MaxIdentifierBytes)
	}
	return nil
}

func copyDocument(document ContractDocument) ContractDocument {
	return ContractDocument{encoded: document.Bytes()}
}
