from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, cast

from process_test_support import INSTALLED_BIN, InstalledProcessTestCase

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.errors import WorkLeaseLostError
from agent_native_runtime.model import WorkItem, parse_timestamp
from agent_native_runtime.process_config import load_process_configuration


class WorkLeaseSourceBoundaryTest(unittest.TestCase):
    def test_worker_driver_is_not_a_production_entrypoint(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        self.assertNotIn("work_lease_driver", pyproject.read_text(encoding="utf-8"))


if INSTALLED_BIN is not None:

    class InstalledWorkLeaseRecoveryTest(InstalledProcessTestCase):
        def worker_command(
            self, mode: str, configuration: Path, owner: str
        ) -> tuple[str, ...]:
            installed = Path(cast(str, INSTALLED_BIN))
            driver = Path(__file__).with_name("work_lease_driver.py")
            return (
                str(installed / "python"),
                str(driver),
                mode,
                str(configuration),
                owner,
            )

        def run_worker(
            self, mode: str, configuration: Path, owner: str
        ) -> dict[str, Any]:
            result = subprocess.run(
                self.worker_command(mode, configuration, owner),
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [line for line in result.stdout.splitlines() if line]
            self.assertEqual(len(lines), 1, result.stdout)
            return cast(dict[str, Any], json.loads(lines[0]))

        def start_holding_worker(
            self, configuration: Path, owner: str
        ) -> tuple[subprocess.Popen[str], dict[str, Any]]:
            process = subprocess.Popen(
                self.worker_command("claim_hold", configuration, owner),
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
                    self.fail(f"worker did not expose a lease: {stderr}")
                marker = cast(dict[str, Any], json.loads(process.stdout.readline()))
                self.assertEqual(marker["stage"], "claimed")
                return process, marker
            finally:
                selector.close()

        def finish_holding_worker(
            self, process: subprocess.Popen[str]
        ) -> dict[str, Any]:
            assert process.stdin is not None
            process.stdin.write("complete\n")
            process.stdin.flush()
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr)
            lines = [line for line in stdout.splitlines() if line]
            self.assertEqual(len(lines), 1, stdout)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            process.stdin.close()
            return cast(dict[str, Any], json.loads(lines[0]))

        def kill_holding_worker(self, process: subprocess.Popen[str]) -> None:
            os.kill(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

        def seed_work(
            self, configuration: Path, command_type: str, *, index: int
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            start = self.start_document()
            start_body, start_token = self.start_request(
                start, jti=f"runtime-lease-start-jti-{index:04d}"
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
            processed = self.run_worker(
                "process_one", configuration, f"seed-start-{index}"
            )
            self.assertTrue(processed["processed"])

            command = self.command_document(start, command_type=command_type)
            command_body, command_token = self.command_request(
                start,
                command,
                jti=f"runtime-lease-command-jti-{index:04d}",
            )
            with self.serving(configuration) as server:
                response = self.post_command(
                    server.port,
                    cast(str, start["runtime_run_id"]),
                    command_body,
                    command_token,
                )
            self.assertEqual(response[0], 202, response[2])
            return start, command

        @staticmethod
        def work_from_marker(marker: dict[str, Any]) -> WorkItem:
            return WorkItem(
                work_id=cast(str, marker["work_id"]),
                runtime_run_id=cast(str, marker["runtime_run_id"]),
                kind=cast(Any, marker["kind"]),
                command_id=cast(str | None, marker["command_id"]),
                lease_owner=cast(str, marker["lease_owner"]),
                lease_token=cast(int, marker["lease_token"]),
                attempt_count=cast(int, marker["attempt_count"]),
                restore_checkpoint=None,
            )

        def test_sigkill_expiry_reclaim_and_stale_fencing(self) -> None:
            for index, command_type in enumerate(("cancel", "checkpoint"), start=1):
                with self.subTest(command_type=command_type):
                    value = self.clone(self.base)
                    state_root = self.root / f"state-lease-{command_type}"
                    value["runtime"]["state_root"] = str(state_root)
                    value["runtime"]["work_lease_seconds"] = 3
                    configuration = self.write_configuration(
                        f"lease-{command_type}.json", value
                    )
                    self.migrate(configuration)
                    start, _ = self.seed_work(configuration, command_type, index=index)

                    owner_a, first = self.start_holding_worker(
                        configuration, f"owner-a-{command_type}"
                    )
                    acquired_monotonic = time.monotonic()
                    first_expiry = parse_timestamp(cast(str, first["lease_expires_at"]))
                    self.kill_holding_worker(owner_a)

                    before = self.run_worker(
                        "claim_once", configuration, f"owner-b-early-{command_type}"
                    )
                    before_expiry_monotonic = time.monotonic()
                    self.assertFalse(before["found"])
                    self.assertLess(datetime.now(UTC), first_expiry)

                    wait_deadline = time.monotonic() + 5
                    reclaim_not_before = first_expiry + timedelta(milliseconds=50)
                    while datetime.now(UTC) < reclaim_not_before:
                        self.assertLess(time.monotonic(), wait_deadline)
                        time.sleep(0.02)

                    owner_b, second = self.start_holding_worker(
                        configuration, f"owner-b-{command_type}"
                    )
                    reclaimed_monotonic = time.monotonic()
                    self.assertEqual(second["work_id"], first["work_id"])
                    self.assertGreater(second["lease_token"], first["lease_token"])
                    self.assertEqual(
                        second["attempt_count"], first["attempt_count"] + 1
                    )
                    self.assertGreater(reclaimed_monotonic, before_expiry_monotonic)
                    self.assertGreater(reclaimed_monotonic, acquired_monotonic)
                    self.assertGreaterEqual(datetime.now(UTC), reclaim_not_before)

                    configuration_value = load_process_configuration(configuration)
                    core = SecureAdmissionCore.open_current(
                        configuration_value.runtime, configuration_value.security
                    )
                    stale_work = self.work_from_marker(first)
                    before_stale = self.state_snapshot(state_root)
                    with self.assertRaises(WorkLeaseLostError):
                        core.kernel.store.release_work(
                            stale_work, "stale-owner", datetime.now(UTC)
                        )
                    self.assertEqual(self.state_snapshot(state_root), before_stale)

                    completed = self.finish_holding_worker(owner_b)
                    self.assertEqual(completed["work_id"], first["work_id"])
                    third = self.run_worker(
                        "claim_once", configuration, f"owner-c-{command_type}"
                    )
                    self.assertFalse(third["found"])
                    with self.assertRaises(WorkLeaseLostError):
                        core.kernel.store.release_work(
                            self.work_from_marker(second),
                            "duplicate-completion",
                            datetime.now(UTC),
                        )

                    with self.serving(configuration):
                        pass
                    counts = self.command_database_counts(state_root)
                    self.assertEqual(counts["runtime_commands"], 1)
                    self.assertEqual(counts["execution_work"], 2)
                    self.assertEqual(counts["runtime_events"], 2)
                    self.assertEqual(
                        counts["checkpoint_manifests"],
                        1 if command_type == "checkpoint" else 0,
                    )
                    status_connection = core.kernel.store._connect(read_only=True)
                    try:
                        status = status_connection.execute(
                            "SELECT status, last_command_sequence, last_event_sequence "
                            "FROM runtime_runs WHERE runtime_run_id = ?",
                            (start["runtime_run_id"],),
                        ).fetchone()
                        work = status_connection.execute(
                            "SELECT state, attempt_count, lease_token FROM execution_work "
                            "WHERE work_id = ?",
                            (first["work_id"],),
                        ).fetchone()
                    finally:
                        status_connection.close()
                    self.assertEqual(status[1:], (1, 2))
                    self.assertEqual(
                        status[0],
                        "cancelled" if command_type == "cancel" else "running",
                    )
                    self.assertEqual(work[0], "completed")
                    self.assertEqual(work[1], 2)
                    self.assertEqual(work[2], second["lease_token"])
                    print(
                        f"work-lease-recovery-case:{command_type}:passed",
                        flush=True,
                    )


if __name__ == "__main__":
    unittest.main()
