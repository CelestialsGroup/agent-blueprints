from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from types import FrameType

from .admission import SecureAdmissionCore
from .errors import RuntimeKernelError
from .http_process import (
    BoundedTLSHTTPServer,
    ProcessState,
    validate_process_documents,
)
from .process_config import (
    ProviderProcessConfiguration,
    check_process_configuration_current,
    load_process_configuration,
    migrate_process_configuration,
    resolve_configuration_path,
)
from .tls import build_server_tls_context


def migrate_main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser("Migrate the Provider-local Native Runtime store explicitly.")
    parsed = parser.parse_args(arguments)
    try:
        configuration = _configuration(parsed.config)
        SecureAdmissionCore.migrate(configuration.runtime, configuration.security)
        migrate_process_configuration(configuration)
    except (OSError, ValueError, RuntimeKernelError) as error:
        _write_failure("MIGRATION_REJECTED", error)
        return 2
    _write_event(
        {
            "event": "migration_complete",
            "configuration_sha256": configuration.source_sha256,
            "schema_version": 2,
        }
    )
    return 0


def serve_main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser("Serve the bounded component-only mTLS Provider process.")
    parsed = parser.parse_args(arguments)
    server: BoundedTLSHTTPServer | None = None
    state = ProcessState()
    try:
        configuration = _configuration(parsed.config)
        core = SecureAdmissionCore.open_current(
            configuration.runtime, configuration.security
        )
        check_process_configuration_current(configuration)
        tls_context = build_server_tls_context(configuration)
        validate_process_documents(configuration, core)
        server = BoundedTLSHTTPServer(configuration, core, tls_context, state)
    except (OSError, ValueError, RuntimeKernelError) as error:
        if server is not None:
            server.server_close()
        _write_failure("SERVE_STARTUP_REJECTED", error)
        return 2

    def stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        server.begin_drain()

    prior_term = signal.signal(signal.SIGTERM, stop)
    prior_int = signal.signal(signal.SIGINT, stop)
    drained = False
    try:
        state.readiness.set()
        address = server.server_address
        _write_event(
            {
                "event": "listener_ready",
                "configuration_sha256": configuration.source_sha256,
                "host": address[0],
                "port": address[1],
                "readiness": True,
                "routes": [
                    "/health/live",
                    "/health/ready",
                    "/v1/capabilities",
                ],
                "tls_minimum": "1.2",
            }
        )
        while not state.stopping.is_set():
            server.handle_request()
    finally:
        server.begin_drain()
        drained = server.wait_for_drain()
        signal.signal(signal.SIGTERM, prior_term)
        signal.signal(signal.SIGINT, prior_int)
        _write_event(
            {
                "event": "listener_stopped",
                "bounded_drain_complete": drained,
                "readiness": False,
                "metrics": state.metrics.snapshot(),
            }
        )
    return 0


def _parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description, allow_abbrev=False)
    parser.add_argument(
        "--config",
        help="Immutable Strict I-JSON process configuration file.",
    )
    return parser


def _configuration(explicit: str | None) -> ProviderProcessConfiguration:
    path = resolve_configuration_path(explicit)
    return load_process_configuration(Path(path))


def _write_failure(code: str, error: BaseException) -> None:
    error_code = (
        error.code if isinstance(error, RuntimeKernelError) else "process_error"
    )
    print(
        json.dumps(
            {"code": code, "error_kind": error_code, "result": "rejected"},
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _write_event(document: dict[str, object]) -> None:
    print(
        json.dumps(document, separators=(",", ":"), sort_keys=True),
        flush=True,
    )
