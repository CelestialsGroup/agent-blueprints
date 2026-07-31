package httpadapter

import (
	"context"
	"net/http"

	"github.com/shell-echo/agent/internal/runtimeport"
)

func (adapter *Adapter) Start(ctx context.Context, request runtimeport.StartRequest) runtimeport.MutationOutcome {
	if request.Validate() != nil {
		// The Port cannot attach a non-fabricated MutationReference to an
		// unconstructed zero request, so its invalid zero remains fail closed.
		return runtimeport.MutationOutcome{}
	}
	return adapter.mutate(
		ctx,
		runtimeport.OperationStart,
		request.Invocation(),
		request.Document(),
		"/v1/runs",
		"",
		adapter.limits.MaxStartRequestBytes,
	)
}

func (adapter *Adapter) Command(ctx context.Context, request runtimeport.CommandRequest) runtimeport.MutationOutcome {
	if request.Validate() != nil {
		return runtimeport.MutationOutcome{}
	}
	invocation := request.Invocation()
	path, rawPath := runtimeRunPath(invocation.RuntimeRunID(), "/commands")
	return adapter.mutate(
		ctx,
		runtimeport.OperationCommand,
		invocation,
		request.Document(),
		path,
		rawPath,
		adapter.limits.MaxCommandRequestBytes,
	)
}

func (adapter *Adapter) mutate(
	ctx context.Context,
	operation runtimeport.Operation,
	invocation runtimeport.Invocation,
	document runtimeport.ContractDocument,
	path string,
	rawPath string,
	maxRequestBytes int,
) runtimeport.MutationOutcome {
	reference, _ := runtimeport.NewMutationReference(invocation)
	if invocation.ProviderRevisionID() != adapter.providerRevisionID || document.Len() > maxRequestBytes ||
		adapter.validator.ValidateMutationRequest(operation, invocation, document.Bytes()) != nil {
		return notDispatched(reference, newFailure(runtimeport.FailureInvalidRequest, codeInvalidRequest, nil))
	}
	target := adapter.target(path, rawPath, "")
	exchange := adapter.execute(
		ctx,
		operation,
		http.MethodPost,
		target,
		invocation.Token().Bytes(),
		document.Bytes(),
		adapter.limits.MutationTimeout,
	)
	if exchange.failure != nil {
		if !exchange.dispatched {
			return notDispatched(reference, *exchange.failure)
		}
		return unknownMutation(reference, *exchange.failure)
	}
	if exchange.statusCode == http.StatusAccepted {
		status, ok := adapter.decodeRunStatus(operation, exchange.body)
		if !ok || status.RuntimeRunID() != invocation.RuntimeRunID() ||
			status.ObservedFencingToken() < invocation.FencingToken() {
			return unknownMutation(reference, newFailure(runtimeport.FailureInvalidResponse, codeInvalidResponse, nil))
		}
		outcome, _ := runtimeport.NewAcceptedMutation(reference, status)
		return outcome
	}
	if class, known := mutationRejectionClass(operation, exchange.statusCode); known {
		failure, ok := adapter.decodeStandardError(class, exchange.body)
		if !ok {
			return unknownMutation(reference, newFailure(runtimeport.FailureInvalidResponse, codeInvalidResponse, nil))
		}
		outcome, _ := runtimeport.NewRejectedMutation(reference, failure)
		return outcome
	}
	if class, uncertain := mutationUncertainHTTPClass(exchange.statusCode); uncertain {
		failure, ok := adapter.decodeStandardError(class, exchange.body)
		if ok {
			return unknownMutation(reference, failure)
		}
	}
	return unknownMutation(reference, newFailure(runtimeport.FailureInvalidResponse, codeInvalidResponse, nil))
}

func mutationRejectionClass(operation runtimeport.Operation, status int) (runtimeport.FailureClass, bool) {
	switch status {
	case http.StatusBadRequest:
		return runtimeport.FailureInvalidRequest, true
	case http.StatusUnauthorized:
		return runtimeport.FailureAuthenticationRejected, true
	case http.StatusForbidden:
		return runtimeport.FailureAuthorityRejected, true
	case http.StatusNotFound:
		return runtimeport.FailureNotFound, operation == runtimeport.OperationCommand
	case http.StatusConflict:
		return runtimeport.FailureProtocolConflict, true
	case http.StatusRequestEntityTooLarge:
		return runtimeport.FailurePayloadTooLarge, true
	case http.StatusUnprocessableEntity:
		return runtimeport.FailureUnsupported, true
	case http.StatusTooManyRequests:
		return runtimeport.FailureThrottled, true
	default:
		return "", false
	}
}

func mutationUncertainHTTPClass(status int) (runtimeport.FailureClass, bool) {
	switch status {
	case http.StatusInternalServerError:
		return runtimeport.FailureInternal, true
	case http.StatusServiceUnavailable:
		return runtimeport.FailureUnavailable, true
	default:
		return "", false
	}
}

func notDispatched(reference runtimeport.MutationReference, failure runtimeport.Failure) runtimeport.MutationOutcome {
	outcome, _ := runtimeport.NewNotDispatchedMutation(reference, failure)
	return outcome
}

func unknownMutation(reference runtimeport.MutationReference, failure runtimeport.Failure) runtimeport.MutationOutcome {
	reconciliation, _ := runtimeport.NewReconciliationRequirement(
		reference,
		[]runtimeport.Operation{runtimeport.OperationReadStatus, runtimeport.OperationReadEvents},
	)
	outcome, _ := runtimeport.NewUnknownMutation(reference, failure, reconciliation)
	return outcome
}

var _ runtimeport.AgentRuntimeProvider = (*Adapter)(nil)
