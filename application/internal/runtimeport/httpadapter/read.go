package httpadapter

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/shell-echo/agent/internal/generated/runtimeapi"
	"github.com/shell-echo/agent/internal/runtimeport"
	"github.com/shell-echo/agent/internal/runtimeport/contractprojection"
)

const (
	codeInvalidRequest   = "ADAPTER_INVALID_REQUEST"
	codeCanceled         = "ADAPTER_CANCELED"
	codeDeadlineExceeded = "ADAPTER_DEADLINE_EXCEEDED"
	codeTransportFailure = "ADAPTER_TRANSPORT_FAILURE"
	codeInvalidResponse  = "ADAPTER_INVALID_RESPONSE"
	codeInternal         = "ADAPTER_INTERNAL"
)

type exchangeResult struct {
	statusCode int
	body       []byte
	dispatched bool
	failure    *runtimeport.Failure
}

func (adapter *Adapter) Capabilities(
	ctx context.Context,
	request runtimeport.CapabilitiesRequest,
) runtimeport.ReadResult[runtimeport.ProviderCapabilities] {
	if request.Validate() != nil || request.ExpectedProviderRevisionID() != adapter.providerRevisionID {
		return readFailure[runtimeport.ProviderCapabilities](runtimeport.FailureInvalidRequest, codeInvalidRequest, nil)
	}
	target := adapter.target("/v1/capabilities", "", "")
	exchange := adapter.execute(ctx, runtimeport.OperationCapabilities, http.MethodGet, target, nil, nil, adapter.limits.CapabilitiesTimeout)
	if exchange.failure != nil {
		return readFailureFrom[runtimeport.ProviderCapabilities](*exchange.failure)
	}
	if exchange.statusCode != http.StatusOK {
		return readHTTPFailure[runtimeport.ProviderCapabilities](adapter, runtimeport.OperationCapabilities, exchange)
	}
	if err := adapter.validator.ValidateSuccessResponse(runtimeport.OperationCapabilities, exchange.body); err != nil {
		return invalidResponse[runtimeport.ProviderCapabilities]()
	}
	var decoded runtimeapi.AgentRuntimeCapabilities
	if err := json.Unmarshal(exchange.body, &decoded); err != nil || decoded.ProviderRevisionID != adapter.providerRevisionID {
		return invalidResponse[runtimeport.ProviderCapabilities]()
	}
	canonical, err := contractprojection.CanonicalizeJSON(exchange.body)
	if err != nil || !adapter.bindCapabilities(sha256.Sum256(canonical)) {
		return invalidResponse[runtimeport.ProviderCapabilities]()
	}
	document, err := runtimeport.NewContractDocument(exchange.body, int(adapter.limits.MaxResponseBytes))
	if err != nil {
		return invalidResponse[runtimeport.ProviderCapabilities]()
	}
	value, err := runtimeport.NewProviderCapabilities(decoded.ProviderRevisionID, document)
	if err != nil {
		return invalidResponse[runtimeport.ProviderCapabilities]()
	}
	return runtimeport.NewReadSuccess(value)
}

func (adapter *Adapter) Status(
	ctx context.Context,
	request runtimeport.StatusRequest,
) runtimeport.ReadResult[runtimeport.RunStatus] {
	if request.Validate() != nil || request.Invocation().ProviderRevisionID() != adapter.providerRevisionID {
		return readFailure[runtimeport.RunStatus](runtimeport.FailureInvalidRequest, codeInvalidRequest, nil)
	}
	invocation := request.Invocation()
	path, rawPath := runtimeRunPath(invocation.RuntimeRunID(), "")
	target := adapter.target(path, rawPath, "")
	exchange := adapter.execute(ctx, runtimeport.OperationReadStatus, http.MethodGet, target, invocation.Token().Bytes(), nil, adapter.limits.ReadTimeout)
	if exchange.failure != nil {
		return readFailureFrom[runtimeport.RunStatus](*exchange.failure)
	}
	if exchange.statusCode != http.StatusOK {
		return readHTTPFailure[runtimeport.RunStatus](adapter, runtimeport.OperationReadStatus, exchange)
	}
	value, ok := adapter.decodeRunStatus(runtimeport.OperationReadStatus, exchange.body)
	if !ok || value.RuntimeRunID() != invocation.RuntimeRunID() ||
		value.ObservedFencingToken() > invocation.FencingToken() {
		return invalidResponse[runtimeport.RunStatus]()
	}
	return runtimeport.NewReadSuccess(value)
}

func (adapter *Adapter) Events(
	ctx context.Context,
	request runtimeport.EventsRequest,
) runtimeport.ReadResult[runtimeport.EventPage] {
	if request.Validate() != nil || request.Invocation().ProviderRevisionID() != adapter.providerRevisionID {
		return readFailure[runtimeport.EventPage](runtimeport.FailureInvalidRequest, codeInvalidRequest, nil)
	}
	invocation := request.Invocation()
	path, rawPath := runtimeRunPath(invocation.RuntimeRunID(), "/events")
	query := "after_event_sequence=" + strconv.FormatUint(request.AfterEventSequence(), 10) +
		"&limit=" + strconv.FormatUint(uint64(request.Limit()), 10)
	target := adapter.target(path, rawPath, query)
	exchange := adapter.execute(ctx, runtimeport.OperationReadEvents, http.MethodGet, target, invocation.Token().Bytes(), nil, adapter.limits.ReadTimeout)
	if exchange.failure != nil {
		return readFailureFrom[runtimeport.EventPage](*exchange.failure)
	}
	if exchange.statusCode != http.StatusOK {
		return readHTTPFailure[runtimeport.EventPage](adapter, runtimeport.OperationReadEvents, exchange)
	}
	value, ok := adapter.decodeEventPage(exchange.body, request)
	if !ok {
		return invalidResponse[runtimeport.EventPage]()
	}
	return runtimeport.NewReadSuccess(value)
}

func (adapter *Adapter) execute(
	ctx context.Context,
	operation runtimeport.Operation,
	method string,
	target *url.URL,
	token []byte,
	body []byte,
	timeout time.Duration,
) exchangeResult {
	if ctx == nil || operation.Validate() != nil || target == nil || timeout <= 0 {
		return localExchangeFailure(runtimeport.FailureInvalidRequest, codeInvalidRequest)
	}
	if operation != runtimeport.OperationCapabilities && !validBearerToken(token, adapter.limits.MaxTokenBytes) {
		return localExchangeFailure(runtimeport.FailureInvalidRequest, codeInvalidRequest)
	}
	if operation == runtimeport.OperationCapabilities && len(token) != 0 {
		return localExchangeFailure(runtimeport.FailureInvalidRequest, codeInvalidRequest)
	}
	requestContext, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if err := requestContext.Err(); err != nil {
		return localExchangeFailure(contextFailureClass(err), contextFailureCode(err))
	}
	request, err := http.NewRequestWithContext(requestContext, method, target.String(), bytes.NewReader(body))
	if err != nil {
		return localExchangeFailure(runtimeport.FailureInvalidRequest, codeInvalidRequest)
	}
	request.Header.Set("Accept", "application/json")
	if len(token) > 0 {
		request.Header.Set("Authorization", "Bearer "+string(token))
	}
	if len(body) > 0 {
		request.Header.Set("Content-Type", "application/json")
		request.ContentLength = int64(len(body))
		request.GetBody = nil
	}

	response, err := adapter.client.Do(request)
	if err != nil {
		if response != nil && response.Body != nil {
			_ = response.Body.Close()
		}
		class := runtimeport.FailureTransport
		code := codeTransportFailure
		if requestContext.Err() != nil {
			class = contextFailureClass(requestContext.Err())
			code = contextFailureCode(requestContext.Err())
		}
		failure := newFailure(class, code, nil)
		return exchangeResult{dispatched: true, failure: &failure}
	}
	encoded, ok := adapter.readBoundedResponse(response, request)
	if !ok {
		failure := newFailure(runtimeport.FailureInvalidResponse, codeInvalidResponse, nil)
		return exchangeResult{dispatched: true, failure: &failure}
	}
	return exchangeResult{statusCode: response.StatusCode, body: encoded, dispatched: true}
}

func (adapter *Adapter) readBoundedResponse(response *http.Response, request *http.Request) ([]byte, bool) {
	if response == nil || response.Body == nil {
		return nil, false
	}
	defer response.Body.Close()
	if response.ProtoMajor != 1 || response.ProtoMinor != 1 || response.Uncompressed ||
		response.Request == nil || response.Request.Method != request.Method || response.Request.URL.String() != request.URL.String() ||
		len(response.TransferEncoding) != 0 || len(response.Trailer) != 0 ||
		len(response.Header.Values("Transfer-Encoding")) != 0 || len(response.Header.Values("Content-Encoding")) != 0 {
		return nil, false
	}
	contentTypes := response.Header.Values("Content-Type")
	contentLengths := response.Header.Values("Content-Length")
	if len(contentTypes) != 1 || contentTypes[0] != "application/json" || len(contentLengths) != 1 {
		return nil, false
	}
	length, err := strconv.ParseInt(contentLengths[0], 10, 64)
	if err != nil || length < 1 || strconv.FormatInt(length, 10) != contentLengths[0] ||
		length != response.ContentLength || length > adapter.limits.MaxResponseBytes {
		return nil, false
	}
	encoded, err := io.ReadAll(io.LimitReader(response.Body, adapter.limits.MaxResponseBytes+1))
	if err != nil || int64(len(encoded)) != length {
		return nil, false
	}
	return encoded, true
}

func readHTTPFailure[T any](adapter *Adapter, operation runtimeport.Operation, exchange exchangeResult) runtimeport.ReadResult[T] {
	class, declared := readFailureClass(operation, exchange.statusCode)
	if !declared {
		return invalidResponse[T]()
	}
	failure, ok := adapter.decodeStandardError(class, exchange.body)
	if !ok {
		return invalidResponse[T]()
	}
	return readFailureFrom[T](failure)
}

func (adapter *Adapter) decodeStandardError(class runtimeport.FailureClass, encoded []byte) (runtimeport.Failure, bool) {
	if adapter.validator.ValidateErrorResponse(encoded) != nil {
		return runtimeport.Failure{}, false
	}
	var decoded runtimeapi.StandardError
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		return runtimeport.Failure{}, false
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(encoded, &raw); err != nil {
		return runtimeport.Failure{}, false
	}
	var details *runtimeport.ContractDocument
	if detailsJSON, exists := raw["details"]; exists {
		document, err := runtimeport.NewContractDocument(detailsJSON, int(adapter.limits.MaxResponseBytes))
		if err != nil {
			return runtimeport.Failure{}, false
		}
		details = &document
	}
	failure, err := runtimeport.NewFailure(class, decoded.Code, details)
	return failure, err == nil
}

func (adapter *Adapter) decodeRunStatus(operation runtimeport.Operation, encoded []byte) (runtimeport.RunStatus, bool) {
	if adapter.validator.ValidateSuccessResponse(operation, encoded) != nil {
		return runtimeport.RunStatus{}, false
	}
	var decoded runtimeapi.AgentRuntimeRunStatus
	if err := json.Unmarshal(encoded, &decoded); err != nil || decoded.LastCommandSequence < 0 ||
		decoded.LastEventSequence < 0 || decoded.ObservedFencingToken < 1 {
		return runtimeport.RunStatus{}, false
	}
	document, err := runtimeport.NewContractDocument(encoded, int(adapter.limits.MaxResponseBytes))
	if err != nil {
		return runtimeport.RunStatus{}, false
	}
	value, err := runtimeport.NewRunStatus(
		decoded.RuntimeRunID,
		runtimeport.RunState(decoded.Status),
		uint64(decoded.LastCommandSequence),
		uint64(decoded.LastEventSequence),
		uint64(decoded.ObservedFencingToken),
		document,
	)
	return value, err == nil
}

func (adapter *Adapter) decodeEventPage(encoded []byte, request runtimeport.EventsRequest) (runtimeport.EventPage, bool) {
	if adapter.validator.ValidateSuccessResponse(runtimeport.OperationReadEvents, encoded) != nil {
		return runtimeport.EventPage{}, false
	}
	var decoded runtimeapi.AgentRuntimeEventPage
	if err := json.Unmarshal(encoded, &decoded); err != nil || decoded.NextEventSequence < 0 ||
		len(decoded.Events) > int(request.Limit()) {
		return runtimeport.EventPage{}, false
	}
	expectedNext := request.AfterEventSequence()
	previous := request.AfterEventSequence()
	for _, event := range decoded.Events {
		if event.RuntimeRunID != request.Invocation().RuntimeRunID() || event.EventSequence < 1 ||
			uint64(event.EventSequence) <= previous || uint64(event.EventSequence) > runtimeport.MaxSafeInteger {
			return runtimeport.EventPage{}, false
		}
		previous = uint64(event.EventSequence)
		expectedNext = previous
	}
	if uint64(decoded.NextEventSequence) != expectedNext {
		return runtimeport.EventPage{}, false
	}
	document, err := runtimeport.NewContractDocument(encoded, int(adapter.limits.MaxResponseBytes))
	if err != nil {
		return runtimeport.EventPage{}, false
	}
	value, err := runtimeport.NewEventPage(request.Invocation().RuntimeRunID(), expectedNext, document)
	return value, err == nil
}

func (adapter *Adapter) bindCapabilities(digest [32]byte) bool {
	adapter.capabilitiesMu.Lock()
	defer adapter.capabilitiesMu.Unlock()
	if !adapter.capabilitiesSeen {
		adapter.capabilitiesDigest = digest
		adapter.capabilitiesSeen = true
		return true
	}
	return adapter.capabilitiesDigest == digest
}

func (adapter *Adapter) target(path, rawPath, rawQuery string) *url.URL {
	target := *adapter.endpoint
	target.Path = path
	target.RawPath = rawPath
	target.RawQuery = rawQuery
	return &target
}

func runtimeRunPath(runtimeRunID, suffix string) (string, string) {
	path := "/v1/runs/" + runtimeRunID + suffix
	rawPath := "/v1/runs/" + url.PathEscape(runtimeRunID) + suffix
	if path == rawPath {
		rawPath = ""
	}
	return path, rawPath
}

func validBearerToken(encoded []byte, maxBytes int) bool {
	if len(encoded) < 5 || len(encoded) > maxBytes {
		return false
	}
	segments := strings.Split(string(encoded), ".")
	if len(segments) != 3 {
		return false
	}
	for _, segment := range segments {
		if segment == "" {
			return false
		}
		for _, character := range segment {
			if (character < 'A' || character > 'Z') && (character < 'a' || character > 'z') &&
				(character < '0' || character > '9') && character != '-' && character != '_' {
				return false
			}
		}
	}
	return true
}

func readFailureClass(operation runtimeport.Operation, status int) (runtimeport.FailureClass, bool) {
	switch status {
	case http.StatusUnauthorized:
		return runtimeport.FailureAuthenticationRejected, true
	case http.StatusForbidden:
		return runtimeport.FailureAuthorityRejected, true
	case http.StatusNotFound:
		return runtimeport.FailureNotFound, operation == runtimeport.OperationReadStatus || operation == runtimeport.OperationReadEvents
	case http.StatusGone:
		return runtimeport.FailureCursorExpired, operation == runtimeport.OperationReadEvents
	case http.StatusInternalServerError:
		return runtimeport.FailureInternal, true
	case http.StatusServiceUnavailable:
		return runtimeport.FailureUnavailable, true
	default:
		return "", false
	}
}

func contextFailureClass(err error) runtimeport.FailureClass {
	if errors.Is(err, context.Canceled) {
		return runtimeport.FailureCanceled
	}
	return runtimeport.FailureDeadlineExceeded
}

func contextFailureCode(err error) string {
	if errors.Is(err, context.Canceled) {
		return codeCanceled
	}
	return codeDeadlineExceeded
}

func localExchangeFailure(class runtimeport.FailureClass, code string) exchangeResult {
	failure := newFailure(class, code, nil)
	return exchangeResult{failure: &failure}
}

func invalidResponse[T any]() runtimeport.ReadResult[T] {
	return readFailure[T](runtimeport.FailureInvalidResponse, codeInvalidResponse, nil)
}

func readFailure[T any](class runtimeport.FailureClass, code string, details *runtimeport.ContractDocument) runtimeport.ReadResult[T] {
	return readFailureFrom[T](newFailure(class, code, details))
}

func readFailureFrom[T any](failure runtimeport.Failure) runtimeport.ReadResult[T] {
	result, err := runtimeport.NewReadFailure[T](failure)
	if err == nil {
		return result
	}
	fallback := newFailure(runtimeport.FailureInternal, codeInternal, nil)
	result, _ = runtimeport.NewReadFailure[T](fallback)
	return result
}

func newFailure(class runtimeport.FailureClass, code string, details *runtimeport.ContractDocument) runtimeport.Failure {
	failure, err := runtimeport.NewFailure(class, code, details)
	if err == nil {
		return failure
	}
	fallback, _ := runtimeport.NewFailure(runtimeport.FailureInternal, codeInternal, nil)
	return fallback
}
