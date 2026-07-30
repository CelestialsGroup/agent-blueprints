from __future__ import annotations

import hashlib
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import (
    CheckpointContentError,
    CheckpointTooLargeError,
    ConfigurationDriftError,
)
from .model import CheckpointManifest, RuntimeConfiguration


@dataclass(frozen=True, slots=True)
class CheckpointObject:
    content_reference: str
    digest: str
    size_bytes: int
    path: Path


@dataclass(frozen=True, slots=True)
class PendingCheckpointObject:
    content_reference: str
    digest: str
    size_bytes: int
    target_directory: Path
    target: Path
    temporary: Path


class CheckpointObjectStore:
    def __init__(self, configuration: RuntimeConfiguration) -> None:
        self._configuration = configuration
        self._objects_root = configuration.state_root / "checkpoint-objects" / "sha256"
        self._temporary_root = configuration.state_root / "checkpoint-objects" / "tmp"

    def prepare(self) -> None:
        for path in (self._objects_root, self._temporary_root):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.chmod(0o700)

    def check_current(self) -> None:
        for path in (self._objects_root, self._temporary_root):
            if not path.is_dir() or path.is_symlink():
                raise ConfigurationDriftError(
                    "checkpoint state directories are not initialized"
                )
            if stat.S_IMODE(path.stat().st_mode) != 0o700:
                raise ConfigurationDriftError(
                    "checkpoint state directory permissions have drifted"
                )

    def write(self, payload: bytes) -> CheckpointObject:
        pending = self.begin_write(payload)
        descriptor = self.open_temporary(pending)
        try:
            try:
                self.write_chunk(descriptor, payload)
                self.fsync_temporary(descriptor)
            finally:
                os.close(descriptor)
            self.publish(pending)
            self.fsync_publish_directories(pending)
            return self.finish_write(pending)
        finally:
            pending.temporary.unlink(missing_ok=True)

    def begin_write(self, payload: bytes) -> PendingCheckpointObject:
        if len(payload) > self._configuration.max_checkpoint_bytes:
            raise CheckpointTooLargeError(
                "checkpoint exceeds the configured byte limit"
            )
        hexadecimal = hashlib.sha256(payload).hexdigest()
        digest = f"sha256:{hexadecimal}"
        target_directory = self._objects_root / hexadecimal[:2]
        target_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_directory.chmod(0o700)
        self._fsync_directory(self._objects_root)
        target = target_directory / hexadecimal
        temporary = self._temporary_root / f"{uuid.uuid4().hex}.partial"
        return PendingCheckpointObject(
            content_reference=f"native-checkpoint://sha256/{hexadecimal}",
            digest=digest,
            size_bytes=len(payload),
            target_directory=target_directory,
            target=target,
            temporary=temporary,
        )

    @staticmethod
    def open_temporary(pending: PendingCheckpointObject) -> int:
        descriptor = os.open(
            pending.temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        return descriptor

    @staticmethod
    def write_chunk(descriptor: int, payload: bytes) -> None:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("checkpoint temporary write made no progress")
            remaining = remaining[written:]

    @staticmethod
    def fsync_temporary(descriptor: int) -> None:
        os.fsync(descriptor)

    def publish(self, pending: PendingCheckpointObject) -> None:
        if pending.target.exists():
            self._verify_path(
                pending.target,
                pending.digest,
                pending.size_bytes,
            )
            pending.temporary.unlink()
            return
        os.replace(pending.temporary, pending.target)

    def fsync_publish_directories(self, pending: PendingCheckpointObject) -> None:
        self._fsync_directory(pending.target_directory)
        self._fsync_directory(self._temporary_root)

    def finish_write(self, pending: PendingCheckpointObject) -> CheckpointObject:
        self._verify_path(pending.target, pending.digest, pending.size_bytes)
        return CheckpointObject(
            content_reference=pending.content_reference,
            digest=pending.digest,
            size_bytes=pending.size_bytes,
            path=pending.target,
        )

    def read_verified(self, manifest: CheckpointManifest) -> bytes:
        manifest.validate()
        hexadecimal = manifest.digest.removeprefix("sha256:")
        expected_reference = f"native-checkpoint://sha256/{hexadecimal}"
        if manifest.content_reference != expected_reference:
            raise CheckpointContentError(
                "checkpoint content reference does not match its digest"
            )
        path = self._objects_root / hexadecimal[:2] / hexadecimal
        self._verify_path(path, manifest.digest, manifest.size_bytes)
        return path.read_bytes()

    def object_paths(self) -> tuple[Path, ...]:
        return tuple(
            sorted(
                path
                for path in self._objects_root.glob("*/*")
                if path.is_file() and len(path.name) == 64
            )
        )

    def _verify_path(self, path: Path, digest: str, size_bytes: int) -> None:
        try:
            stat = path.stat()
        except FileNotFoundError as error:
            raise CheckpointContentError("checkpoint content is missing") from error
        if stat.st_size != size_bytes:
            raise CheckpointContentError(
                "checkpoint content size does not match its manifest"
            )
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise CheckpointContentError(
                "checkpoint content digest does not match its manifest"
            )

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
