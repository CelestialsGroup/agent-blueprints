from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.process_config import load_process_configuration


class TestExecutor:
    def start(self, runtime_run_id: str, restored_state: bytes | None) -> None:
        del runtime_run_id, restored_state

    def cancel(self, runtime_run_id: str) -> str:
        return f"test-executor://cancellation/{runtime_run_id}"

    def checkpoint(self, runtime_run_id: str) -> bytes:
        return f"checkpoint-payload:{runtime_run_id}".encode("ascii")


def _emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, separators=(",", ":"), sort_keys=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("mode", choices=("process_one", "claim_once", "claim_hold"))
    parser.add_argument("configuration")
    parser.add_argument("owner")
    arguments = parser.parse_args()

    configuration = load_process_configuration(Path(arguments.configuration))
    core = SecureAdmissionCore.open_current(
        configuration.runtime, configuration.security
    )
    if arguments.mode == "process_one":
        processed = core.kernel.process_one(TestExecutor(), owner=arguments.owner)
        _emit({"processed": processed, "stage": "processed"})
        return 0

    work = core.kernel.store.claim_work(arguments.owner, core.kernel.clock())
    if work is None:
        _emit({"found": False, "stage": "claim_once"})
        return 0

    connection = core.kernel.store._connect(read_only=True)
    try:
        lease_expires_at = cast(
            str,
            connection.execute(
                "SELECT lease_expires_at FROM execution_work WHERE work_id = ?",
                (work.work_id,),
            ).fetchone()[0],
        )
    finally:
        connection.close()
    _emit(
        {
            "attempt_count": work.attempt_count,
            "command_id": work.command_id,
            "found": True,
            "kind": work.kind,
            "lease_expires_at": lease_expires_at,
            "lease_owner": work.lease_owner,
            "lease_token": work.lease_token,
            "runtime_run_id": work.runtime_run_id,
            "stage": "claimed" if arguments.mode == "claim_hold" else "claim_once",
            "work_id": work.work_id,
        }
    )
    if arguments.mode == "claim_once":
        return 0
    if sys.stdin.readline() != "complete\n":
        return 2
    core.kernel._process_claimed_work(work, TestExecutor())
    _emit({"stage": "completed", "work_id": work.work_id})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
