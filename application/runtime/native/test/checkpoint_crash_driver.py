from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

from work_lease_driver import TestExecutor

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.model import WorkItem
from agent_native_runtime.process_config import load_process_configuration

STAGES = (
    "partial_write",
    "full_write",
    "file_fsync",
    "renamed",
    "directory_fsync",
    "manifest_before_commit",
    "manifest_after_commit",
)


def _emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, separators=(",", ":"), sort_keys=True), flush=True)


def _hold(document: dict[str, Any]) -> NoReturn:
    _emit(document)
    sys.stdin.readline()
    raise RuntimeError("checkpoint crash driver must be terminated by SIGKILL")


def _lease_expiry(core: SecureAdmissionCore, work: WorkItem) -> str:
    connection = core.kernel.store._connect(read_only=True)
    try:
        return cast(
            str,
            connection.execute(
                "SELECT lease_expires_at FROM execution_work WHERE work_id = ?",
                (work.work_id,),
            ).fetchone()[0],
        )
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("configuration")
    parser.add_argument("owner")
    arguments = parser.parse_args()

    configuration = load_process_configuration(Path(arguments.configuration))
    core = SecureAdmissionCore.open_current(
        configuration.runtime, configuration.security
    )
    work = core.kernel.store.claim_work(arguments.owner, core.kernel.clock())
    if work is None or work.kind != "checkpoint":
        raise RuntimeError("checkpoint work is unavailable")
    lease_expires_at = _lease_expiry(core, work)
    payload = TestExecutor().checkpoint(work.runtime_run_id)
    pending = core.kernel.checkpoints.begin_write(payload)
    descriptor = core.kernel.checkpoints.open_temporary(pending)
    split = max(1, len(payload) // 2)
    core.kernel.checkpoints.write_chunk(descriptor, payload[:split])
    marker: dict[str, Any] = {
        "digest": pending.digest,
        "lease_expires_at": lease_expires_at,
        "runtime_run_id": work.runtime_run_id,
        "size_bytes": pending.size_bytes,
        "stage": arguments.stage,
        "work_id": work.work_id,
    }
    if arguments.stage == "partial_write":
        _hold(marker | {"temporary_size": split})

    core.kernel.checkpoints.write_chunk(descriptor, payload[split:])
    if arguments.stage == "full_write":
        _hold(marker | {"temporary_size": len(payload)})

    core.kernel.checkpoints.fsync_temporary(descriptor)
    if arguments.stage == "file_fsync":
        _hold(marker | {"temporary_size": len(payload)})

    os.close(descriptor)
    core.kernel.checkpoints.publish(pending)
    if arguments.stage == "renamed":
        _hold(marker | {"target_exists": pending.target.exists()})

    core.kernel.checkpoints.fsync_publish_directories(pending)
    checkpoint_object = core.kernel.checkpoints.finish_write(pending)
    if arguments.stage == "directory_fsync":
        _hold(marker | {"target_exists": checkpoint_object.path.exists()})

    manifest = core.kernel._checkpoint_manifest(work, checkpoint_object)
    manifest_digest = core.kernel.store.checkpoint_manifest_digest(manifest)
    completed_at = core.kernel.clock()
    with core.kernel.store._transaction() as connection:
        core.kernel.store._complete_checkpoint_transaction(
            connection,
            work,
            manifest,
            manifest_digest,
            completed_at,
        )
        if arguments.stage == "manifest_before_commit":
            _hold(marker | {"checkpoint_id": manifest.checkpoint_id})
    if arguments.stage == "manifest_after_commit":
        _hold(marker | {"checkpoint_id": manifest.checkpoint_id})
    raise AssertionError(f"unhandled checkpoint crash stage: {arguments.stage}")


if __name__ == "__main__":
    raise SystemExit(main())
