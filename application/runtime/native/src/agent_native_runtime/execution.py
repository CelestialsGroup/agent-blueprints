from __future__ import annotations

from typing import Protocol


class ExecutionLoop(Protocol):
    """Replaceable private loop whose methods are idempotent by runtime_run_id.

    A process may stop after a side effect and before durable work completion,
    so repeated Start, Cancel, and Checkpoint calls must return compatible facts.
    No transport or Platform authority types cross this Port.
    """

    def start(self, runtime_run_id: str, restored_state: bytes | None) -> None: ...

    def cancel(self, runtime_run_id: str) -> str: ...

    def checkpoint(self, runtime_run_id: str) -> bytes: ...
