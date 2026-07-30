from __future__ import annotations

import hashlib
import json
import os
import selectors
import signal
import sqlite3
import subprocess
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, cast

from process_test_support import INSTALLED_BIN, InstalledProcessTestCase

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.model import parse_timestamp
from agent_native_runtime.process_config import load_process_configuration

CRASH_STAGES = (
    "partial_write",
    "full_write",
    "file_fsync",
    "renamed",
    "directory_fsync",
    "manifest_before_commit",
    "manifest_after_commit",
)


class CheckpointCrashSourceBoundaryTest(unittest.TestCase):
    def test_checkpoint_driver_is_not_a_production_entrypoint(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        self.assertNotIn(
            "checkpoint_crash_driver", pyproject.read_text(encoding="utf-8")
        )


if INSTALLED_BIN is not None:

    class InstalledCheckpointCrashConsistencyTest(InstalledProcessTestCase):
        def worker_command(self, configuration: Path, owner: str) -> tuple[str, ...]:
            installed = Path(cast(str, INSTALLED_BIN))
            driver = Path(__file__).with_name("work_lease_driver.py")
            return (
                str(installed / "python"),
                str(driver),
                "process_one",
                str(configuration),
                owner,
            )

        def run_worker(self, configuration: Path, owner: str) -> bool:
            result = subprocess.run(
                self.worker_command(configuration, owner),
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [line for line in result.stdout.splitlines() if line]
            self.assertEqual(len(lines), 1, result.stdout)
            marker = cast(dict[str, Any], json.loads(lines[0]))
            self.assertEqual(marker["stage"], "processed")
            return cast(bool, marker["processed"])

        def crash_command(
            self, stage: str, configuration: Path, owner: str
        ) -> tuple[str, ...]:
            installed = Path(cast(str, INSTALLED_BIN))
            driver = Path(__file__).with_name("checkpoint_crash_driver.py")
            return (
                str(installed / "python"),
                str(driver),
                stage,
                str(configuration),
                owner,
            )

        def start_crash_driver(
            self, stage: str, configuration: Path, owner: str
        ) -> tuple[subprocess.Popen[str], dict[str, Any]]:
            process = subprocess.Popen(
                self.crash_command(stage, configuration, owner),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(cast(BinaryIO, process.stdout), selectors.EVENT_READ)
            try:
                if not selector.select(timeout=15):
                    process.kill()
                    _, stderr = process.communicate(timeout=5)
                    self.fail(f"checkpoint driver did not expose {stage}: {stderr}")
                marker = cast(dict[str, Any], json.loads(process.stdout.readline()))
                self.assertEqual(marker["stage"], stage)
                return process, marker
            finally:
                selector.close()

        def kill_crash_driver(self, process: subprocess.Popen[str]) -> None:
            os.kill(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

        def seed_checkpoint(self, configuration: Path, *, index: int) -> dict[str, Any]:
            start = self.start_document()
            start_body, start_token = self.start_request(
                start, jti=f"checkpoint-crash-start-jti-{index:04d}"
            )
            with self.serving(configuration) as server:
                response = self.request(
                    server.port,
                    self.pki.client,
                    "/v1/runs",
                    method="POST",
                    body=start_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {start_token}",
                    },
                )
            self.assertEqual(response[0], 202, response[2])
            self.assertTrue(self.run_worker(configuration, f"seed-start-{index}"))

            command = self.command_document(start, command_type="checkpoint")
            command_body, command_token = self.command_request(
                start,
                command,
                jti=f"checkpoint-crash-command-jti-{index:04d}",
            )
            with self.serving(configuration) as server:
                response = self.post_command(
                    server.port,
                    cast(str, start["runtime_run_id"]),
                    command_body,
                    command_token,
                )
            self.assertEqual(response[0], 202, response[2])
            return start

        @staticmethod
        def temporary_files(state_root: Path) -> tuple[Path, ...]:
            return tuple(
                sorted((state_root / "checkpoint-objects" / "tmp").glob("*.partial"))
            )

        @staticmethod
        def checkpoint_work(state_root: Path) -> tuple[str, int]:
            connection = sqlite3.connect(state_root / "runtime.sqlite3")
            try:
                row = connection.execute(
                    "SELECT state, attempt_count FROM execution_work "
                    "WHERE kind = 'checkpoint'"
                ).fetchone()
                return cast(tuple[str, int], row)
            finally:
                connection.close()

        def wait_for_expiry(self, encoded_expiry: str) -> None:
            expiry = parse_timestamp(encoded_expiry)
            not_before = expiry + timedelta(milliseconds=50)
            deadline = time.monotonic() + 3
            while datetime.now(UTC) < not_before:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)

        def test_sigkill_checkpoint_filesystem_and_manifest_windows(self) -> None:
            for index, stage in enumerate(CRASH_STAGES, start=1):
                with self.subTest(stage=stage):
                    value = self.clone(self.base)
                    state_root = self.root / f"state-checkpoint-{stage}"
                    value["runtime"]["state_root"] = str(state_root)
                    value["runtime"]["work_lease_seconds"] = 1
                    configuration = self.write_configuration(
                        f"checkpoint-{stage}.json", value
                    )
                    self.migrate(configuration)
                    start = self.seed_checkpoint(configuration, index=index)

                    process, marker = self.start_crash_driver(
                        stage, configuration, f"owner-a-{stage}"
                    )
                    self.kill_crash_driver(process)

                    configuration_value = load_process_configuration(configuration)
                    core = SecureAdmissionCore.open_current(
                        configuration_value.runtime,
                        configuration_value.security,
                    )
                    counts = self.command_database_counts(state_root)
                    committed = stage == "manifest_after_commit"
                    self.assertEqual(counts["runtime_commands"], 1)
                    self.assertEqual(counts["execution_work"], 2)
                    self.assertEqual(counts["runtime_events"], 2 if committed else 1)
                    self.assertEqual(
                        counts["checkpoint_manifests"], 1 if committed else 0
                    )
                    self.assertEqual(
                        self.checkpoint_work(state_root),
                        ("completed", 1) if committed else ("processing", 1),
                    )

                    temporary = self.temporary_files(state_root)
                    if stage in {"partial_write", "full_write", "file_fsync"}:
                        self.assertEqual(len(temporary), 1)
                        self.assertEqual(
                            temporary[0].stat().st_size,
                            cast(int, marker["temporary_size"]),
                        )
                        self.assertEqual(len(core.kernel.checkpoints.object_paths()), 0)
                    else:
                        self.assertEqual(temporary, ())
                        self.assertEqual(len(core.kernel.checkpoints.object_paths()), 1)

                    if committed:
                        self.assertFalse(
                            self.run_worker(configuration, f"owner-b-{stage}")
                        )
                    else:
                        self.wait_for_expiry(cast(str, marker["lease_expires_at"]))
                        self.assertTrue(
                            self.run_worker(configuration, f"owner-b-{stage}")
                        )
                    self.assertFalse(self.run_worker(configuration, f"owner-c-{stage}"))

                    with self.serving(configuration):
                        pass
                    recovered = SecureAdmissionCore.open_current(
                        configuration_value.runtime,
                        configuration_value.security,
                    )
                    final_counts = self.command_database_counts(state_root)
                    self.assertEqual(final_counts["runtime_commands"], 1)
                    self.assertEqual(final_counts["execution_work"], 2)
                    self.assertEqual(final_counts["runtime_events"], 2)
                    self.assertEqual(final_counts["checkpoint_manifests"], 1)
                    self.assertEqual(
                        self.checkpoint_work(state_root),
                        ("completed", 1 if committed else 2),
                    )
                    self.assertEqual(
                        len(recovered.kernel.checkpoints.object_paths()), 1
                    )

                    status = recovered.kernel.status(cast(str, start["runtime_run_id"]))
                    self.assertEqual(status.status, "running")
                    self.assertEqual(status.last_command_sequence, 1)
                    self.assertEqual(status.last_event_sequence, 2)
                    self.assertIsNotNone(status.checkpoint)
                    manifest = status.checkpoint
                    assert manifest is not None
                    self.assertEqual(manifest.portability, "same_revision")
                    self.assertEqual(
                        manifest.provider_revision_id,
                        configuration_value.runtime.provider_revision_id,
                    )
                    self.assertEqual(
                        manifest.source_runtime_revision,
                        configuration_value.runtime.runtime_revision,
                    )
                    self.assertEqual(
                        manifest.compatibility_profile,
                        configuration_value.runtime.checkpoint_profile,
                    )
                    content = recovered.kernel.checkpoints.read_verified(manifest)
                    self.assertEqual(len(content), manifest.size_bytes)
                    self.assertEqual(
                        "sha256:" + hashlib.sha256(content).hexdigest(),
                        manifest.digest,
                    )
                    self.assertEqual(manifest.digest, marker["digest"])
                    print(
                        f"checkpoint-crash-consistency-case:{stage}:passed",
                        flush=True,
                    )


if __name__ == "__main__":
    unittest.main()
