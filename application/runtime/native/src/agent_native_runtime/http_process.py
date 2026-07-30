from __future__ import annotations

import http.client
import json
import secrets
import socket
import socketserver
import sqlite3
import ssl
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, BinaryIO, Literal, cast
from urllib.parse import urlsplit

from .admission import SecureAdmissionCore
from .errors import (
    AuthorizationBindingError,
    CheckpointError,
    CommandSequenceError,
    ConfigurationError,
    ContractSchemaError,
    CursorExpiredError,
    DigestMismatchError,
    EncodedBodyTooLargeError,
    IdempotencyConflictError,
    InvalidMutationError,
    MutationReplayError,
    RuntimeRunConflictError,
    RuntimeRunNotFoundError,
    StaleFencingError,
    StateConflictError,
    StrictJsonError,
    TokenValidationError,
    UnsupportedOperationError,
)
from .model import (
    EventPage,
    RuntimeEvent,
    RuntimeStatus,
    event_data_to_document,
    format_timestamp,
)
from .process_config import ProviderProcessConfiguration
from .tls import (
    AuthenticatedCaller,
    PeerCertificateError,
    PeerIdentityNotAllowedError,
    authenticate_peer_certificate,
)

START_PATH = "/v1/runs"
START_ENCODED_BODY_LIMIT = 8 * 1024 * 1024
COMMAND_ENCODED_BODY_LIMIT = 256 * 1024
_COMMAND_REQUEST_PREFIX = b"POST /v1/runs/"
_COMMAND_REQUEST_SUFFIX = b"/commands HTTP/1.1\r\n"
_READ_REQUEST_PREFIX = b"GET /v1/runs/"
_READ_REQUEST_SUFFIX = b" HTTP/1.1\r\n"
_BODY_READ_CHUNK_BYTES = 64 * 1024
RUN_STATUS_SCHEMA_ID = "urn:agent-platform:agent-runtime-run-status:v1"
EVENT_PAGE_SCHEMA_ID = "urn:agent-platform:agent-runtime-event-page:v1"
STANDARD_ERROR_SCHEMA_ID = "urn:agent-platform:standard-error:v1"


@dataclass(frozen=True, slots=True)
class _HTTPErrorResponse:
    status: HTTPStatus
    code: str
    message: str
    retryable: bool
    retry_after: int | None = None
    details: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class _ReadRequestTarget:
    operation: Literal["read_status", "read_events"]
    runtime_run_id: str
    after_event_sequence: int = 0
    limit: int = 1000


def _parse_content_length(values: list[str]) -> int | None:
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("duplicate content length")
    value = values[0]
    if (
        not value
        or not value.isascii()
        or not value.isdigit()
        or (len(value) > 1 and value.startswith("0"))
        or len(value) > 20
    ):
        raise ValueError("invalid content length")
    return int(value, 10)


def _is_exact_start_request_line(raw_requestline: bytes) -> bool:
    return raw_requestline == b"POST /v1/runs HTTP/1.1\r\n"


def _targets_start_boundary(command: str, path: str) -> bool:
    target = urlsplit(path)
    return (command == "POST" and target.path in {START_PATH, START_PATH + "/"}) or (
        command != "POST" and path == START_PATH
    )


def _parse_exact_command_request_line(raw_requestline: bytes) -> str | None:
    if not (
        raw_requestline.startswith(_COMMAND_REQUEST_PREFIX)
        and raw_requestline.endswith(_COMMAND_REQUEST_SUFFIX)
    ):
        return None
    encoded = raw_requestline[
        len(_COMMAND_REQUEST_PREFIX) : -len(_COMMAND_REQUEST_SUFFIX)
    ]
    rejected = b"/%?\\#"
    if not encoded or any(
        byte < 0x21 or byte > 0x7E or byte in rejected for byte in encoded
    ):
        return None
    return encoded.decode("ascii")


def _targets_command_boundary(command: str, path: str) -> bool:
    target = urlsplit(path)
    candidate = target.path
    return candidate.startswith("/v1/runs/") and (
        candidate.endswith("/commands") or candidate.endswith("/commands/")
    )


def _parse_canonical_query_integer(
    encoded: bytes, *, minimum: int, maximum: int
) -> int | None:
    if (
        not encoded
        or len(encoded) > 16
        or any(byte < ord("0") or byte > ord("9") for byte in encoded)
        or (len(encoded) > 1 and encoded.startswith(b"0"))
    ):
        return None
    value = int(encoded, 10)
    return value if minimum <= value <= maximum else None


def _parse_exact_read_request_line(
    raw_requestline: bytes,
) -> _ReadRequestTarget | None:
    if not (
        raw_requestline.startswith(_READ_REQUEST_PREFIX)
        and raw_requestline.endswith(_READ_REQUEST_SUFFIX)
    ):
        return None
    encoded_target = raw_requestline[
        len(_READ_REQUEST_PREFIX) : -len(_READ_REQUEST_SUFFIX)
    ]
    if not encoded_target or any(
        byte < 0x21 or byte > 0x7E or byte in b"\\#%" for byte in encoded_target
    ):
        return None
    path, separator, query = encoded_target.partition(b"?")
    if b"?" in query:
        return None

    if b"/" not in path:
        if separator or len(path) > 200:
            return None
        return _ReadRequestTarget("read_status", path.decode("ascii"))

    runtime_run_id, route_separator, suffix = path.partition(b"/")
    if (
        not runtime_run_id
        or len(runtime_run_id) > 200
        or route_separator != b"/"
        or suffix != b"events"
        or b"/" in runtime_run_id
    ):
        return None
    if not separator:
        return _ReadRequestTarget("read_events", runtime_run_id.decode("ascii"))
    if not query:
        return None

    values: dict[bytes, int] = {}
    for parameter in query.split(b"&"):
        name, equals, encoded_value = parameter.partition(b"=")
        if not equals or name in values:
            return None
        if name == b"after_event_sequence":
            value = _parse_canonical_query_integer(
                encoded_value, minimum=0, maximum=9_007_199_254_740_991
            )
        elif name == b"limit":
            value = _parse_canonical_query_integer(
                encoded_value, minimum=1, maximum=1000
            )
        else:
            return None
        if value is None:
            return None
        values[name] = value
    return _ReadRequestTarget(
        "read_events",
        runtime_run_id.decode("ascii"),
        after_event_sequence=values.get(b"after_event_sequence", 0),
        limit=values.get(b"limit", 1000),
    )


def _parse_bearer_authorization(values: list[str], *, max_token_bytes: int) -> str:
    if len(values) != 1:
        raise ValueError("exactly one authorization value is required")
    value = values[0]
    if not value.startswith("Bearer "):
        raise ValueError("authorization scheme is not Bearer")
    token = value.removeprefix("Bearer ")
    if (
        not token
        or value != f"Bearer {token}"
        or not token.isascii()
        or len(token) > max_token_bytes
    ):
        raise ValueError("bearer token is not bounded ASCII")
    segments = token.split(".")
    if len(segments) != 3 or any(not segment for segment in segments):
        raise ValueError("bearer token is not compact JWS")
    admitted = frozenset(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
    if any(character not in admitted for segment in segments for character in segment):
        raise ValueError("bearer token contains invalid base64url characters")
    return token


def _runtime_status_document(status: RuntimeStatus) -> dict[str, Any]:
    document: dict[str, Any] = {
        "runtime_run_id": status.runtime_run_id,
        "tenant_id": status.tenant_id,
        "conversation_id": status.conversation_id,
        "work_order_id": status.work_order_id,
        "workflow_run_id": status.workflow_run_id,
        "agent_run_id": status.agent_run_id,
        "status": status.status,
        "last_command_sequence": status.last_command_sequence,
        "last_event_sequence": status.last_event_sequence,
        "observed_fencing_token": status.observed_fencing_token,
        "updated_at": format_timestamp(status.updated_at),
    }
    if status.checkpoint is not None:
        document["checkpoint"] = status.checkpoint.to_document()
    if status.completed_at is not None:
        document["completed_at"] = format_timestamp(status.completed_at)
    return document


def _runtime_event_document(event: RuntimeEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "runtime_run_id": event.runtime_run_id,
        "event_sequence": event.event_sequence,
        "type": event.type,
        "occurred_at": format_timestamp(event.occurred_at),
        "data_version": event.data_version,
        "data": event_data_to_document(event.data),
        "source_cursor": event.source_cursor,
    }


def _event_page_document(page: EventPage) -> dict[str, Any]:
    return {
        "events": [_runtime_event_document(event) for event in page.events],
        "next_event_sequence": page.next_event_sequence,
    }


def _sqlite_is_temporarily_unavailable(error: sqlite3.OperationalError) -> bool:
    error_code = getattr(error, "sqlite_errorcode", None)
    if not isinstance(error_code, int):
        return False
    return error_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


def _start_error_response(error: Exception) -> _HTTPErrorResponse:
    if isinstance(error, EncodedBodyTooLargeError):
        return _HTTPErrorResponse(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "START_BODY_TOO_LARGE",
            "The encoded Runtime Start request exceeds its limit.",
            False,
        )
    if isinstance(error, TokenValidationError):
        return _HTTPErrorResponse(
            HTTPStatus.UNAUTHORIZED,
            "RUNTIME_TOKEN_REJECTED",
            "Runtime invocation token is not admitted.",
            False,
        )
    if isinstance(error, AuthorizationBindingError):
        return _HTTPErrorResponse(
            HTTPStatus.FORBIDDEN,
            "RUNTIME_AUTHORIZATION_REJECTED",
            "Runtime Start authorization is not admitted.",
            False,
        )
    if isinstance(
        error,
        (
            IdempotencyConflictError,
            MutationReplayError,
            RuntimeRunConflictError,
            StateConflictError,
        ),
    ):
        return _HTTPErrorResponse(
            HTTPStatus.CONFLICT,
            "RUNTIME_START_CONFLICT",
            "Runtime Start conflicts with an accepted mutation.",
            False,
        )
    if isinstance(error, (UnsupportedOperationError, CheckpointError)):
        return _HTTPErrorResponse(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "RUNTIME_START_UNSUPPORTED",
            "Runtime Start requests unsupported execution semantics.",
            False,
        )
    if isinstance(
        error,
        (
            StrictJsonError,
            ContractSchemaError,
            DigestMismatchError,
            InvalidMutationError,
        ),
    ):
        return _HTTPErrorResponse(
            HTTPStatus.BAD_REQUEST,
            "RUNTIME_START_REJECTED",
            "Runtime Start request is not admitted.",
            False,
        )
    if isinstance(error, sqlite3.OperationalError) and (
        _sqlite_is_temporarily_unavailable(error)
    ):
        return _HTTPErrorResponse(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "PROVIDER_TEMPORARILY_UNAVAILABLE",
            "Runtime Provider is temporarily unavailable.",
            True,
            1,
        )
    return _HTTPErrorResponse(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "Runtime Provider encountered an internal error.",
        False,
    )


def _command_error_response(error: Exception) -> _HTTPErrorResponse:
    if isinstance(error, EncodedBodyTooLargeError):
        return _HTTPErrorResponse(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            "COMMAND_BODY_TOO_LARGE",
            "The encoded Runtime Command request exceeds its limit.",
            False,
        )
    if isinstance(error, TokenValidationError):
        return _HTTPErrorResponse(
            HTTPStatus.UNAUTHORIZED,
            "RUNTIME_TOKEN_REJECTED",
            "Runtime invocation token is not admitted.",
            False,
        )
    if isinstance(error, AuthorizationBindingError):
        return _HTTPErrorResponse(
            HTTPStatus.FORBIDDEN,
            "RUNTIME_AUTHORIZATION_REJECTED",
            "Runtime Command authorization is not admitted.",
            False,
        )
    if isinstance(error, RuntimeRunNotFoundError):
        return _HTTPErrorResponse(
            HTTPStatus.NOT_FOUND,
            "RUNTIME_RUN_NOT_FOUND",
            "The admitted RuntimeRun does not exist in this Provider.",
            False,
        )
    if isinstance(
        error,
        (
            CommandSequenceError,
            IdempotencyConflictError,
            MutationReplayError,
            RuntimeRunConflictError,
            StaleFencingError,
            StateConflictError,
        ),
    ):
        return _HTTPErrorResponse(
            HTTPStatus.CONFLICT,
            "RUNTIME_COMMAND_CONFLICT",
            "Runtime Command conflicts with accepted durable state.",
            False,
        )
    if isinstance(error, (UnsupportedOperationError, CheckpointError)):
        return _HTTPErrorResponse(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "RUNTIME_COMMAND_UNSUPPORTED",
            "Runtime Command requests unsupported Provider semantics.",
            False,
        )
    if isinstance(
        error,
        (
            StrictJsonError,
            ContractSchemaError,
            DigestMismatchError,
            InvalidMutationError,
        ),
    ):
        return _HTTPErrorResponse(
            HTTPStatus.BAD_REQUEST,
            "RUNTIME_COMMAND_REJECTED",
            "Runtime Command request is not admitted.",
            False,
        )
    if isinstance(error, sqlite3.OperationalError) and (
        _sqlite_is_temporarily_unavailable(error)
    ):
        return _HTTPErrorResponse(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "PROVIDER_TEMPORARILY_UNAVAILABLE",
            "Runtime Provider is temporarily unavailable.",
            True,
            1,
        )
    return _HTTPErrorResponse(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "Runtime Provider encountered an internal error.",
        False,
    )


def _read_error_response(error: Exception) -> _HTTPErrorResponse:
    if isinstance(error, TokenValidationError):
        return _HTTPErrorResponse(
            HTTPStatus.UNAUTHORIZED,
            "RUNTIME_TOKEN_REJECTED",
            "Runtime invocation token is not admitted.",
            False,
        )
    if isinstance(error, (AuthorizationBindingError, StaleFencingError)):
        return _HTTPErrorResponse(
            HTTPStatus.FORBIDDEN,
            "RUNTIME_AUTHORIZATION_REJECTED",
            "Runtime read authorization is not admitted.",
            False,
        )
    if isinstance(error, RuntimeRunNotFoundError):
        return _HTTPErrorResponse(
            HTTPStatus.NOT_FOUND,
            "RUNTIME_RUN_NOT_FOUND",
            "The admitted RuntimeRun does not exist in this Provider.",
            False,
        )
    if isinstance(error, CursorExpiredError):
        return _HTTPErrorResponse(
            HTTPStatus.GONE,
            "EVENT_CURSOR_EXPIRED",
            "The Runtime event cursor is no longer retained.",
            False,
            details={
                "work_order_id": error.work_order_id,
                "requested_after_event_sequence": error.requested_after,
                "earliest_available_event_sequence": error.earliest_available,
                "latest_available_event_sequence": error.latest_available,
                "recovery": "latest_compatible_checkpoint_or_platform_canonical_event_history",
            },
        )
    if isinstance(error, sqlite3.OperationalError) and (
        _sqlite_is_temporarily_unavailable(error)
    ):
        return _HTTPErrorResponse(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "PROVIDER_TEMPORARILY_UNAVAILABLE",
            "Runtime Provider is temporarily unavailable.",
            True,
            1,
        )
    return _HTTPErrorResponse(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "Runtime Provider encountered an internal error.",
        False,
    )


@dataclass(slots=True)
class ProcessMetrics:
    accepted_connections: int = 0
    connection_limit_rejections: int = 0
    request_limit_rejections: int = 0
    handshake_timeouts: int = 0
    handshake_rejections: int = 0
    idle_timeouts: int = 0
    read_timeouts: int = 0
    write_timeouts: int = 0
    completed_requests: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def increment(self, name: str) -> None:
        with self._lock:
            setattr(self, name, cast(int, getattr(self, name)) + 1)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                name: cast(int, getattr(self, name))
                for name in (
                    "accepted_connections",
                    "connection_limit_rejections",
                    "request_limit_rejections",
                    "handshake_timeouts",
                    "handshake_rejections",
                    "idle_timeouts",
                    "read_timeouts",
                    "write_timeouts",
                    "completed_requests",
                )
            }


@dataclass(slots=True)
class ProcessState:
    readiness: threading.Event = field(default_factory=threading.Event)
    stopping: threading.Event = field(default_factory=threading.Event)
    metrics: ProcessMetrics = field(default_factory=ProcessMetrics)

    def begin_drain(self) -> None:
        self.readiness.clear()
        self.stopping.set()


class _BoundedHeaderReader:
    def __init__(self, source: BinaryIO, *, max_bytes: int, max_count: int) -> None:
        self._source = source
        self._max_bytes = max_bytes
        self._max_count = max_count
        self._bytes = 0
        self._count = 0

    def readline(self, size: int = -1) -> bytes:
        remaining = self._max_bytes - self._bytes
        if remaining < 0:
            raise http.client.LineTooLong("HTTP headers exceed the byte limit")
        admitted_size = remaining + 1
        if size >= 0:
            admitted_size = min(admitted_size, size)
        line = self._source.readline(admitted_size)
        self._bytes += len(line)
        self._count += 1
        if self._bytes > self._max_bytes:
            raise http.client.LineTooLong("HTTP headers exceed the byte limit")
        if self._count > self._max_count + 1:
            raise http.client.LineTooLong("HTTP headers exceed the count limit")
        return line


class BoundedTLSHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(
        self,
        configuration: ProviderProcessConfiguration,
        core: SecureAdmissionCore,
        tls_context: ssl.SSLContext,
        state: ProcessState,
    ) -> None:
        self.configuration = configuration
        self.core = core
        self.tls_context = tls_context
        self.process_state = state
        self.request_queue_size = configuration.limits.listen_backlog
        self._connection_slots = threading.BoundedSemaphore(
            configuration.limits.max_connections
        )
        self.request_slots = threading.BoundedSemaphore(
            configuration.limits.max_concurrent_requests
        )
        self._active: set[ssl.SSLSocket] = set()
        self._active_condition = threading.Condition()
        super().__init__(
            (configuration.bind_host, configuration.bind_port),
            ProviderRequestHandler,
            bind_and_activate=False,
        )
        try:
            self.server_bind()
            self.server_activate()
        except BaseException:
            self.server_close()
            raise
        self.timeout = 0.1

    def get_request(self) -> tuple[socket.socket, Any]:
        raw, address = self.socket.accept()
        raw.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_SNDBUF,
            self.configuration.limits.socket_send_buffer_bytes,
        )
        raw.settimeout(self.configuration.limits.tls_handshake_timeout_ms / 1_000)
        try:
            secured = self.tls_context.wrap_socket(
                raw, server_side=True, do_handshake_on_connect=False
            )
            secured.do_handshake()
        except TimeoutError:
            self.process_state.metrics.increment("handshake_timeouts")
            raw.close()
            raise OSError("bounded TLS handshake timed out") from None
        except ssl.SSLError:
            self.process_state.metrics.increment("handshake_rejections")
            raw.close()
            raise OSError("TLS handshake rejected") from None
        secured.settimeout(self.configuration.limits.idle_timeout_ms / 1_000)
        return secured, address

    def process_request(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: Any,
    ) -> None:
        secured = cast(ssl.SSLSocket, request)
        if not self._connection_slots.acquire(blocking=False):
            self.process_state.metrics.increment("connection_limit_rejections")
            self._send_capacity_rejection(secured)
            self.shutdown_request(secured)
            return
        with self._active_condition:
            self._active.add(secured)
            self.process_state.metrics.increment("accepted_connections")
        thread = threading.Thread(
            target=self._bounded_process_request_thread,
            args=(secured, client_address),
            name="native-runtime-http-connection",
            daemon=True,
        )
        thread.start()

    def _bounded_process_request_thread(
        self, request: ssl.SSLSocket, client_address: Any
    ) -> None:
        try:
            self.process_request_thread(request, client_address)
        finally:
            with self._active_condition:
                self._active.discard(request)
                self._active_condition.notify_all()
            self._connection_slots.release()

    def _send_capacity_rejection(self, request: ssl.SSLSocket) -> None:
        document = _standard_error_document(
            "PROVIDER_CONNECTION_LIMIT",
            "Provider connection capacity is exhausted.",
            retryable=True,
        )
        self.core.projection.validate(STANDARD_ERROR_SCHEMA_ID, document)
        body = _encode_json(document)
        response = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\nRetry-After: 1\r\n\r\n"
            + body
        )
        try:
            request.settimeout(self.configuration.limits.write_timeout_ms / 1_000)
            request.sendall(response)
        except (OSError, ssl.SSLError, TimeoutError):
            pass

    def handle_error(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: Any,
    ) -> None:
        del request, client_address

    def begin_drain(self) -> None:
        self.process_state.begin_drain()
        self.server_close()

    def wait_for_drain(self) -> bool:
        deadline = time.monotonic() + self.configuration.limits.drain_timeout_ms / 1_000
        with self._active_condition:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._active_condition.wait(timeout=remaining)
            drained = not self._active
            active = tuple(self._active)
        if not drained:
            for request in active:
                with suppress(OSError):
                    request.shutdown(socket.SHUT_RDWR)
                request.close()
        return drained


class ProviderRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AgentNativeRuntime"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self._request_count = 0
        self._content_length: int | None = None
        self._command_runtime_run_id: str | None = None
        self._read_target: _ReadRequestTarget | None = None
        self.authenticated_caller: AuthenticatedCaller | None = None
        self.peer_error: PeerCertificateError | None = None
        server = self._provider_server
        certificate = cast(ssl.SSLSocket, self.connection).getpeercert(binary_form=True)
        try:
            self.authenticated_caller = authenticate_peer_certificate(
                certificate or b"", server.configuration
            )
        except PeerCertificateError as error:
            self.peer_error = error

    @property
    def _provider_server(self) -> BoundedTLSHTTPServer:
        return cast(BoundedTLSHTTPServer, self.server)

    def handle_one_request(self) -> None:
        server = self._provider_server
        limits = server.configuration.limits
        if self._request_count >= limits.max_requests_per_connection:
            self.close_connection = True
            return
        self.connection.settimeout(limits.idle_timeout_ms / 1_000)
        try:
            self.raw_requestline = self.rfile.readline(
                limits.max_request_line_bytes + 1
            )
        except TimeoutError:
            server.process_state.metrics.increment("idle_timeouts")
            self.close_connection = True
            return
        if len(self.raw_requestline) > limits.max_request_line_bytes:
            self.request_version = "HTTP/1.1"
            self.command = ""
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_REQUEST_LINE_REJECTED",
                "The HTTP request line exceeds its admitted bound.",
                retryable=False,
            )
            return
        if not self.raw_requestline:
            self.close_connection = True
            return
        if not server.request_slots.acquire(blocking=False):
            server.process_state.metrics.increment("request_limit_rejections")
            self.request_version = "HTTP/1.1"
            self.command = ""
            self.close_connection = True
            is_start = (
                self.authenticated_caller is not None
                and self.peer_error is None
                and _is_exact_start_request_line(self.raw_requestline)
            )
            is_command = (
                self.authenticated_caller is not None
                and self.peer_error is None
                and _parse_exact_command_request_line(self.raw_requestline) is not None
            )
            self._send_standard_error(
                HTTPStatus.TOO_MANY_REQUESTS
                if is_start or is_command
                else HTTPStatus.SERVICE_UNAVAILABLE,
                (
                    "PROVIDER_START_CONCURRENCY_LIMIT"
                    if is_start
                    else "PROVIDER_COMMAND_CONCURRENCY_LIMIT"
                )
                if is_start or is_command
                else "PROVIDER_CONCURRENCY_LIMIT",
                (
                    "Runtime Start concurrency is exhausted."
                    if is_start
                    else "Runtime Command concurrency is exhausted."
                )
                if is_start or is_command
                else "Provider request concurrency is exhausted.",
                retryable=True,
                retry_after=1,
            )
            return
        original_reader = self.rfile
        try:
            self.connection.settimeout(limits.read_timeout_ms / 1_000)
            self.rfile = cast(
                Any,
                _BoundedHeaderReader(
                    cast(BinaryIO, original_reader),
                    max_bytes=limits.max_header_bytes,
                    max_count=limits.max_header_count,
                ),
            )
            try:
                parsed = self.parse_request()
            except TimeoutError:
                server.process_state.metrics.increment("read_timeouts")
                self.close_connection = True
                return
            finally:
                self.rfile = original_reader
            if not parsed:
                return
            self._request_count += 1
            if self._request_count >= limits.max_requests_per_connection:
                self.close_connection = True
            if self.request_version != "HTTP/1.1":
                self.close_connection = True
                self._send_standard_error(
                    HTTPStatus.BAD_REQUEST,
                    "HTTP_VERSION_REJECTED",
                    "Only HTTP/1.1 is admitted.",
                    retryable=False,
                )
                return
            if _targets_start_boundary(self.command, self.path) and not (
                _is_exact_start_request_line(self.raw_requestline)
            ):
                self.close_connection = True
                self._send_standard_error(
                    HTTPStatus.BAD_REQUEST,
                    "HTTP_START_TARGET_REJECTED",
                    "Runtime Start requires exact POST /v1/runs over HTTP/1.1.",
                    retryable=False,
                )
                return
            self._command_runtime_run_id = _parse_exact_command_request_line(
                self.raw_requestline
            )
            self._read_target = _parse_exact_read_request_line(self.raw_requestline)
            if _targets_command_boundary(self.command, self.path) and (
                self._command_runtime_run_id is None
            ):
                self.close_connection = True
                self._send_standard_error(
                    HTTPStatus.BAD_REQUEST,
                    "HTTP_COMMAND_TARGET_REJECTED",
                    "Runtime Command requires an exact dynamic origin-form target over HTTP/1.1.",
                    retryable=False,
                )
                return
            if not self._validate_host_and_framing():
                return
            if self.peer_error is not None:
                code = (
                    HTTPStatus.FORBIDDEN
                    if isinstance(self.peer_error, PeerIdentityNotAllowedError)
                    else HTTPStatus.UNAUTHORIZED
                )
                self._send_standard_error(
                    code,
                    "WORKLOAD_IDENTITY_REJECTED",
                    "Workload identity is not admitted.",
                    retryable=False,
                )
                return
            method = getattr(self, "do_" + self.command, None)
            if method is None:
                self._route_not_enabled()
                return
            method()
            server.process_state.metrics.increment("completed_requests")
        except TimeoutError:
            server.process_state.metrics.increment("write_timeouts")
            self.close_connection = True
        except (BrokenPipeError, ConnectionError, ssl.SSLError):
            self.close_connection = True
        finally:
            server.request_slots.release()

    def do_GET(self) -> None:
        read_target = getattr(self, "_read_target", None)
        if read_target is not None:
            self._handle_read(read_target)
            return
        target = urlsplit(self.path)
        if target.query or target.fragment:
            self._route_not_enabled()
            return
        if target.path == "/v1/capabilities":
            self._send_json(
                HTTPStatus.OK,
                self._provider_server.configuration.capabilities_document(),
            )
            return
        if target.path == "/health/live":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if target.path == "/health/ready":
            if self._provider_server.process_state.readiness.is_set():
                self._send_json(HTTPStatus.OK, {"status": "ready"})
            else:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"status": "not_ready"},
                    retry_after=1,
                )
            return
        self._route_not_enabled()

    def do_POST(self) -> None:
        if self.path == START_PATH:
            self._handle_start()
            return
        runtime_run_id = getattr(self, "_command_runtime_run_id", None)
        if runtime_run_id is not None:
            self._handle_command(runtime_run_id)
            return
        self._route_not_enabled()

    def _mutation_request(
        self, *, operation: str, encoded_limit: int, body_too_large_code: str
    ) -> tuple[bytes, str, AuthenticatedCaller] | None:
        if not self._provider_server.process_state.readiness.is_set():
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "PROVIDER_NOT_READY",
                f"Runtime Provider is not accepting {operation} requests.",
                retryable=True,
                retry_after=1,
            )
            return None
        content_types = self.headers.get_all("Content-Type", failobj=[])
        if content_types != ["application/json"]:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_CONTENT_TYPE_REJECTED",
                "Content-Type must be application/json.",
                retryable=False,
            )
            return None
        if self._content_length is None:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_FRAMING_REJECTED",
                "Exactly one Content-Length is required.",
                retryable=False,
            )
            return None
        if self._content_length > encoded_limit:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                body_too_large_code,
                f"The encoded Runtime {operation} request exceeds its limit.",
                retryable=False,
            )
            return None
        try:
            compact_jws = _parse_bearer_authorization(
                self.headers.get_all("Authorization", failobj=[]),
                max_token_bytes=self._provider_server.configuration.security.max_token_bytes,
            )
        except ValueError:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.UNAUTHORIZED,
                "RUNTIME_TOKEN_REJECTED",
                "Runtime invocation token is not admitted.",
                retryable=False,
            )
            return None
        encoded_body = self._read_exact_body(self._content_length)
        if encoded_body is None:
            return None
        caller = self.authenticated_caller
        if caller is None:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.UNAUTHORIZED,
                "WORKLOAD_IDENTITY_REJECTED",
                "Workload identity is not admitted.",
                retryable=False,
            )
            return None
        return encoded_body, compact_jws, caller

    def _handle_start(self) -> None:
        request = self._mutation_request(
            operation="Start",
            encoded_limit=START_ENCODED_BODY_LIMIT,
            body_too_large_code="START_BODY_TOO_LARGE",
        )
        if request is None:
            return
        encoded_body, compact_jws, caller = request
        try:
            status = self._provider_server.core.start(
                encoded_body,
                compact_jws,
                authenticated_caller=caller.token_subject,
            )
        except Exception as error:
            response = _start_error_response(error)
            self._send_standard_error(
                response.status,
                response.code,
                response.message,
                retryable=response.retryable,
                retry_after=response.retry_after,
            )
            return
        self._send_status(status, HTTPStatus.ACCEPTED)

    def _handle_command(self, runtime_run_id: str) -> None:
        request = self._mutation_request(
            operation="Command",
            encoded_limit=COMMAND_ENCODED_BODY_LIMIT,
            body_too_large_code="COMMAND_BODY_TOO_LARGE",
        )
        if request is None:
            return
        encoded_body, compact_jws, caller = request
        try:
            status = self._provider_server.core.submit_command(
                runtime_run_id,
                encoded_body,
                compact_jws,
                authenticated_caller=caller.token_subject,
            )
        except Exception as error:
            response = _command_error_response(error)
            self._send_standard_error(
                response.status,
                response.code,
                response.message,
                retryable=response.retryable,
                retry_after=response.retry_after,
            )
            return
        self._send_status(status, HTTPStatus.ACCEPTED)

    def _read_request(self, operation: str) -> tuple[str, AuthenticatedCaller] | None:
        if not self._provider_server.process_state.readiness.is_set():
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "PROVIDER_NOT_READY",
                f"Runtime Provider is not accepting {operation} requests.",
                retryable=True,
                retry_after=1,
            )
            return None
        try:
            compact_jws = _parse_bearer_authorization(
                self.headers.get_all("Authorization", failobj=[]),
                max_token_bytes=self._provider_server.configuration.security.max_token_bytes,
            )
        except ValueError:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.UNAUTHORIZED,
                "RUNTIME_TOKEN_REJECTED",
                "Runtime invocation token is not admitted.",
                retryable=False,
            )
            return None
        caller = self.authenticated_caller
        if caller is None:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.UNAUTHORIZED,
                "WORKLOAD_IDENTITY_REJECTED",
                "Workload identity is not admitted.",
                retryable=False,
            )
            return None
        return compact_jws, caller

    def _handle_read(self, target: _ReadRequestTarget) -> None:
        request = self._read_request(
            "Status" if target.operation == "read_status" else "Event"
        )
        if request is None:
            return
        compact_jws, caller = request
        try:
            if target.operation == "read_status":
                status = self._provider_server.core.status(
                    target.runtime_run_id,
                    compact_jws,
                    authenticated_caller=caller.token_subject,
                )
                self._send_status(status, HTTPStatus.OK)
                return
            page = self._provider_server.core.events(
                target.runtime_run_id,
                compact_jws,
                authenticated_caller=caller.token_subject,
                after_event_sequence=target.after_event_sequence,
                limit=target.limit,
            )
        except Exception as error:
            response = _read_error_response(error)
            self._send_standard_error(
                response.status,
                response.code,
                response.message,
                retryable=response.retryable,
                retry_after=response.retry_after,
                details=response.details,
            )
            return
        self._send_event_page(page)

    def _send_status(self, status: RuntimeStatus, response_status: HTTPStatus) -> None:
        document = _runtime_status_document(status)
        try:
            self._provider_server.core.projection.validate(
                RUN_STATUS_SCHEMA_ID, document
            )
        except Exception:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "RESPONSE_VALIDATION_FAILED",
                "Runtime Provider could not encode its response.",
                retryable=False,
            )
            return
        self._send_json(response_status, document)

    def _send_event_page(self, page: EventPage) -> None:
        document = _event_page_document(page)
        try:
            self._provider_server.core.projection.validate(
                EVENT_PAGE_SCHEMA_ID, document
            )
        except Exception:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "RESPONSE_VALIDATION_FAILED",
                "Runtime Provider could not encode its response.",
                retryable=False,
            )
            return
        self._send_json(HTTPStatus.OK, document)

    def do_PUT(self) -> None:
        self._route_not_enabled()

    def do_DELETE(self) -> None:
        self._route_not_enabled()

    def _validate_host_and_framing(self) -> bool:
        hosts = self.headers.get_all("Host", failobj=[])
        if len(hosts) != 1:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_HOST_REJECTED",
                "Exactly one local Host header is required.",
                retryable=False,
            )
            return False
        port = cast(tuple[str, int], self.server.server_address)[1]
        admitted_hosts = {
            "localhost",
            f"localhost:{port}",
            "127.0.0.1",
            f"127.0.0.1:{port}",
        }
        if hosts[0].lower() not in admitted_hosts:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_HOST_REJECTED",
                "Host does not match the bounded listener.",
                retryable=False,
            )
            return False
        if self.headers.get_all("Transfer-Encoding", failobj=[]):
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_FRAMING_REJECTED",
                "Transfer-Encoding is not admitted by this process foundation.",
                retryable=False,
            )
            return False
        if self.headers.get_all("Expect", failobj=[]):
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_FRAMING_REJECTED",
                "Expect is not admitted.",
                retryable=False,
            )
            return False
        try:
            self._content_length = _parse_content_length(
                self.headers.get_all("Content-Length", failobj=[])
            )
        except ValueError:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_FRAMING_REJECTED",
                "Content-Length is invalid or ambiguous.",
                retryable=False,
            )
            return False
        if self._content_length not in (None, 0) and not (
            self.command == "POST"
            and (
                self.path == START_PATH
                or getattr(self, "_command_runtime_run_id", None) is not None
            )
            and self.request_version == "HTTP/1.1"
        ):
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "REQUEST_BODY_NOT_ADMITTED",
                "This route does not admit a request body.",
                retryable=False,
            )
            return False
        return True

    def _read_exact_body(self, content_length: int) -> bytes | None:
        deadline = (
            time.monotonic()
            + self._provider_server.configuration.limits.read_timeout_ms / 1_000
        )
        remaining = content_length
        chunks: list[bytes] = []
        while remaining:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                self._body_read_failed(timeout=True)
                return None
            self.connection.settimeout(timeout)
            try:
                chunk = self.rfile.read(min(remaining, _BODY_READ_CHUNK_BYTES))
            except TimeoutError:
                self._body_read_failed(timeout=True)
                return None
            if not chunk:
                self._body_read_failed(timeout=False)
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _body_read_failed(self, *, timeout: bool) -> None:
        self.close_connection = True
        if timeout:
            self._provider_server.process_state.metrics.increment("read_timeouts")
        self._send_standard_error(
            HTTPStatus.BAD_REQUEST,
            "HTTP_BODY_READ_REJECTED",
            "The encoded request body was not received within its bounds.",
            retryable=False,
        )

    def handle_expect_100(self) -> bool:
        self.close_connection = True
        self._send_standard_error(
            HTTPStatus.BAD_REQUEST,
            "HTTP_FRAMING_REJECTED",
            "Expect is not admitted.",
            retryable=False,
        )
        return False

    def _route_not_enabled(self) -> None:
        self._send_standard_error(
            HTTPStatus.NOT_FOUND,
            "ROUTE_NOT_ENABLED",
            "The requested route is not enabled in this component slice.",
            retryable=False,
        )

    def _send_json(
        self,
        status: HTTPStatus,
        document: dict[str, Any],
        *,
        retry_after: int | None = None,
    ) -> None:
        body = _encode_json(document)
        if len(body) > self._provider_server.configuration.limits.max_response_bytes:
            self._send_standard_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "RESPONSE_LIMIT_EXCEEDED",
                "The bounded response cannot be encoded.",
                retryable=False,
            )
            return
        self._write_json_response(status, body, retry_after=retry_after)

    def _send_standard_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        *,
        retryable: bool,
        retry_after: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        document = _standard_error_document(
            code, message, retryable=retryable, details=details
        )
        self._provider_server.core.projection.validate(
            STANDARD_ERROR_SCHEMA_ID, document
        )
        body = _encode_json(document)
        self._write_json_response(status, body, retry_after=retry_after)

    def _write_json_response(
        self, status: HTTPStatus, body: bytes, *, retry_after: int | None
    ) -> None:
        limit = self._provider_server.configuration.limits.max_response_bytes
        if len(body) > limit:
            self.close_connection = True
            return
        self.connection.settimeout(
            self._provider_server.configuration.limits.write_timeout_ms / 1_000
        )
        self.send_response_only(status.value, status.phrase)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.send_header(
            "Connection", "close" if self.close_connection else "keep-alive"
        )
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        del code, message, explain
        self.close_connection = True
        self._send_standard_error(
            HTTPStatus.BAD_REQUEST,
            "HTTP_REQUEST_REJECTED",
            "The HTTP request is outside the admitted bounds.",
            retryable=False,
        )

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _encode_json(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")


def _standard_error_document(
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, object] | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "trace_id": secrets.token_hex(16),
    }
    if details is not None:
        document["details"] = details
    return document


def validate_process_documents(
    configuration: ProviderProcessConfiguration, core: SecureAdmissionCore
) -> None:
    capabilities = configuration.capabilities_document()
    core.projection.validate(
        "urn:agent-platform:agent-runtime-capabilities:v1", capabilities
    )
    encoded = json.dumps(
        capabilities, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    if len(encoded) > configuration.limits.max_response_bytes:
        raise ConfigurationError(
            "Capabilities exceed the configured response body limit"
        )
    standard_error = _standard_error_document(
        "CONFIGURATION_VALIDATION",
        "Configuration validation.",
        retryable=False,
    )
    core.projection.validate(STANDARD_ERROR_SCHEMA_ID, standard_error)
