from __future__ import annotations

import base64
import json
import os
import selectors
import signal
import socket
import subprocess
import time
import unittest
from pathlib import Path
from typing import Any, BinaryIO, cast

from process_test_support import (
    CALLER_SUBJECT,
    INSTALLED_BIN,
    InstalledProcessTestCase,
    RawHTTPConnection,
)


class CommandTransactionSourceBoundaryTest(unittest.TestCase):
    def test_recovery_driver_is_test_only(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        declared = pyproject.read_text(encoding="utf-8")
        self.assertNotIn("command_transaction_driver", declared)


if INSTALLED_BIN is not None:

    class InstalledCommandTransactionRecoveryTest(InstalledProcessTestCase):
        def seed_start(self, configuration: Path, *, jti: str) -> dict[str, Any]:
            document = self.start_document()
            body, token = self.start_request(document, jti=jti)
            with self.serving(configuration) as server:
                response = self.request(
                    server.port,
                    self.pki.client,
                    "/v1/runs",
                    method="POST",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
            self.assertEqual(response[0], 202, response[2])
            self.assertEqual(json.loads(response[2])["status"], "accepted")
            return document

        def write_driver_request(
            self,
            name: str,
            runtime_run_id: str,
            body: bytes,
            token: str,
        ) -> Path:
            path = self.root / f"transaction-request-{name}.json"
            path.write_text(
                json.dumps(
                    {
                        "authenticated_caller": CALLER_SUBJECT,
                        "compact_jws": token,
                        "encoded_body_base64": base64.b64encode(body).decode("ascii"),
                        "runtime_run_id": runtime_run_id,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            return path

        def kill_at_marker(
            self, mode: str, configuration: Path, request: Path
        ) -> dict[str, str]:
            installed = Path(cast(str, INSTALLED_BIN))
            driver = Path(__file__).with_name("command_transaction_driver.py")
            process = subprocess.Popen(
                (
                    str(installed / "python"),
                    str(driver),
                    mode,
                    str(configuration),
                    str(request),
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(cast(BinaryIO, process.stdout), selectors.EVENT_READ)
            try:
                ready = selector.select(timeout=15)
                if not ready:
                    process.kill()
                    _, stderr = process.communicate(timeout=5)
                    self.fail(f"transaction driver did not reach marker: {stderr}")
                marker = cast(dict[str, str], json.loads(process.stdout.readline()))
                self.assertEqual(marker["stage"], mode)
                os.kill(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, -signal.SIGKILL)
                self.assertEqual(stdout, "")
                self.assertEqual(stderr, "")
                return marker
            finally:
                selector.close()
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

        def retry_command(
            self,
            configuration: Path,
            start: dict[str, Any],
            command: dict[str, Any],
            *,
            jti: str,
        ) -> dict[str, Any]:
            body, token = self.command_request(start, command, jti=jti)
            with self.serving(configuration) as server:
                response = self.post_command(
                    server.port,
                    cast(str, start["runtime_run_id"]),
                    body,
                    token,
                )
            self.assertEqual(response[0], 202, response[2])
            return cast(dict[str, Any], json.loads(response[2]))

        def test_sigkill_transaction_windows_reopen_and_replay(self) -> None:
            expectations = {
                "before_transaction": (1, 0, 1, "accepted"),
                "before_commit": (1, 0, 1, "accepted"),
                "after_commit": (2, 1, 2, "cancel_requested"),
            }
            for index, mode in enumerate(expectations, start=1):
                with self.subTest(mode=mode):
                    value = self.clone(self.base)
                    state_root = self.root / f"state-transaction-{mode}"
                    value["runtime"]["state_root"] = str(state_root)
                    configuration = self.write_configuration(
                        f"transaction-{mode}.json", value
                    )
                    self.migrate(configuration)
                    start = self.seed_start(
                        configuration,
                        jti=f"runtime-transaction-start-jti-{index:04d}",
                    )
                    command = self.command_document(start)
                    body, token = self.command_request(
                        start,
                        command,
                        jti=f"runtime-transaction-command-jti-{index:04d}",
                    )
                    request = self.write_driver_request(
                        mode,
                        cast(str, start["runtime_run_id"]),
                        body,
                        token,
                    )
                    self.kill_at_marker(mode, configuration, request)

                    with self.serving(configuration):
                        pass
                    counts = self.command_database_counts(state_root)
                    expected_jtis, expected_commands, expected_work, expected_status = (
                        expectations[mode]
                    )
                    self.assertEqual(counts["consumed_mutation_jtis"], expected_jtis)
                    self.assertEqual(counts["runtime_commands"], expected_commands)
                    self.assertEqual(counts["execution_work"], expected_work)
                    self.assertEqual(counts["runtime_events"], 1)

                    replay = self.retry_command(
                        configuration,
                        start,
                        command,
                        jti=f"runtime-transaction-retry-jti-{index:04d}",
                    )
                    self.assertEqual(replay["status"], "cancel_requested")
                    self.assertEqual(replay["last_command_sequence"], 1)
                    self.assertEqual(replay["last_event_sequence"], 1)
                    final_counts = self.command_database_counts(state_root)
                    self.assertEqual(final_counts["runtime_commands"], 1)
                    self.assertEqual(final_counts["execution_work"], 2)
                    self.assertEqual(final_counts["runtime_events"], 1)
                    self.assertEqual(
                        final_counts["consumed_mutation_jtis"],
                        3 if expected_status == "cancel_requested" else 2,
                    )
                    print(
                        f"command-transaction-recovery-case:{mode}:passed",
                        flush=True,
                    )

        def test_http_response_loss_reopens_and_replays_without_duplicates(
            self,
        ) -> None:
            value = self.clone(self.base)
            state_root = self.root / "state-command-response-loss"
            value["runtime"]["state_root"] = str(state_root)
            configuration = self.write_configuration(
                "command-response-loss.json", value
            )
            self.migrate(configuration)
            start = self.seed_start(
                configuration, jti="runtime-response-loss-start-jti-0001"
            )
            command = self.command_document(start)
            body, token = self.command_request(
                start, command, jti="runtime-response-loss-command-jti-0001"
            )
            route = f"/v1/runs/{start['runtime_run_id']}/commands"
            with self.serving(configuration) as server:
                raw = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                raw.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + f"Authorization: Bearer {token}\r\n".encode("ascii")
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body,
                )
                raw.connection.shutdown(socket.SHUT_RDWR)
                raw.connection.close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if (
                        self.command_database_counts(state_root)["runtime_commands"]
                        == 1
                    ):
                        break
                    time.sleep(0.02)
                else:
                    self.fail("Command did not commit after client response loss")

            replay = self.retry_command(
                configuration,
                start,
                command,
                jti="runtime-response-loss-retry-jti-0002",
            )
            self.assertEqual(replay["status"], "cancel_requested")
            counts = self.command_database_counts(state_root)
            self.assertEqual(counts["consumed_mutation_jtis"], 3)
            self.assertEqual(counts["runtime_commands"], 1)
            self.assertEqual(counts["execution_work"], 2)
            self.assertEqual(counts["runtime_events"], 1)
            print(
                "command-transaction-recovery-case:http_response_loss:passed",
                flush=True,
            )


if __name__ == "__main__":
    unittest.main()
