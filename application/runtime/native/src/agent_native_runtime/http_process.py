from __future__ import annotations

import http.client
import json
import secrets
import socket
import socketserver
import ssl
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, BinaryIO, cast
from urllib.parse import urlsplit

from .admission import SecureAdmissionCore
from .errors import ConfigurationError
from .process_config import ProviderProcessConfiguration
from .tls import (
    AuthenticatedCaller,
    PeerCertificateError,
    PeerIdentityNotAllowedError,
    authenticate_peer_certificate,
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
        body = _standard_error_body(
            "PROVIDER_CONNECTION_LIMIT",
            "Provider connection capacity is exhausted.",
            retryable=True,
        )
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
            self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
            return
        if not self.raw_requestline:
            self.close_connection = True
            return
        if not server.request_slots.acquire(blocking=False):
            server.process_state.metrics.increment("request_limit_rejections")
            self.request_version = "HTTP/1.1"
            self.command = ""
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "PROVIDER_CONCURRENCY_LIMIT",
                "Provider request concurrency is exhausted.",
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
                    HTTPStatus.HTTP_VERSION_NOT_SUPPORTED,
                    "HTTP_VERSION_REJECTED",
                    "Only HTTP/1.1 is admitted.",
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
        self._route_not_enabled()

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
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) > 1:
            self.close_connection = True
            self._send_standard_error(
                HTTPStatus.BAD_REQUEST,
                "HTTP_FRAMING_REJECTED",
                "Duplicate Content-Length is rejected.",
                retryable=False,
            )
            return False
        if lengths:
            if not lengths[0].isascii() or not lengths[0].isdigit():
                self.close_connection = True
                self._send_standard_error(
                    HTTPStatus.BAD_REQUEST,
                    "HTTP_FRAMING_REJECTED",
                    "Content-Length is invalid.",
                    retryable=False,
                )
                return False
            if int(lengths[0], 10) != 0:
                self.close_connection = True
                self._send_standard_error(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "REQUEST_BODY_NOT_ADMITTED",
                    "These foundation routes do not admit a request body.",
                    retryable=False,
                )
                return False
        return True

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
        body = json.dumps(
            document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
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
    ) -> None:
        body = _standard_error_body(code, message, retryable=retryable)
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
        del message, explain
        try:
            status = HTTPStatus(code)
        except ValueError:
            status = HTTPStatus.BAD_REQUEST
        self.close_connection = True
        self._send_standard_error(
            status,
            "HTTP_REQUEST_REJECTED",
            "The HTTP request is outside the admitted bounds.",
            retryable=False,
        )

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _standard_error_body(code: str, message: str, *, retryable: bool) -> bytes:
    return json.dumps(
        {
            "code": code,
            "message": message,
            "retryable": retryable,
            "trace_id": secrets.token_hex(16),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


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
    standard_error = json.loads(
        _standard_error_body(
            "CONFIGURATION_VALIDATION",
            "Configuration validation.",
            retryable=False,
        )
    )
    core.projection.validate("urn:agent-platform:standard-error:v1", standard_error)
