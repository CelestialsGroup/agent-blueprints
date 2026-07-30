from __future__ import annotations

import argparse
import base64
import json
import signal
from pathlib import Path
from typing import Any, Never, cast

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.process_config import load_process_configuration


def _marker(stage: str) -> None:
    print(json.dumps({"stage": stage}, separators=(",", ":")), flush=True)


def _await_sigkill() -> Never:
    while True:
        signal.pause()


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument(
        "mode", choices=("before_transaction", "before_commit", "after_commit")
    )
    parser.add_argument("configuration", type=Path)
    parser.add_argument("request", type=Path)
    arguments = parser.parse_args()

    configuration = load_process_configuration(arguments.configuration)
    core = SecureAdmissionCore.open_current(
        configuration.runtime, configuration.security
    )
    request = cast(
        dict[str, Any], json.loads(arguments.request.read_text(encoding="utf-8"))
    )
    encoded_body = base64.b64decode(
        cast(str, request["encoded_body_base64"]), validate=True
    )
    mutation, admission, admitted_at = core.admit_command(
        cast(str, request["runtime_run_id"]),
        encoded_body,
        cast(str, request["compact_jws"]),
        authenticated_caller=cast(str, request["authenticated_caller"]),
    )
    if arguments.mode == "before_transaction":
        _marker("before_transaction")
        _await_sigkill()

    connection = core.kernel.store._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        core.kernel.store._submit_command_transaction(
            connection, mutation, admission, admitted_at
        )
        if arguments.mode == "before_commit":
            _marker("before_commit")
            _await_sigkill()
        connection.execute("COMMIT")
        _marker("after_commit")
        _await_sigkill()
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
