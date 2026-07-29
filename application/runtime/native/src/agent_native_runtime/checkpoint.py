from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import CheckpointContentError, CheckpointTooLargeError
from .model import CheckpointManifest, RuntimeConfiguration


@dataclass(frozen=True, slots=True)
class CheckpointObject:
    content_reference: str
    digest: str
    size_bytes: int
    path: Path


class CheckpointObjectStore:
    def __init__(self, configuration: RuntimeConfiguration) -> None:
        self._configuration = configuration
        self._objects_root = configuration.state_root / "checkpoint-objects" / "sha256"
        self._temporary_root = configuration.state_root / "checkpoint-objects" / "tmp"
        for path in (self._objects_root, self._temporary_root):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.chmod(0o700)

    def write(self, payload: bytes) -> CheckpointObject:
        if len(payload) > self._configuration.max_checkpoint_bytes:
            raise CheckpointTooLargeError(
                "checkpoint exceeds the configured byte limit"
            )
        hexadecimal = hashlib.sha256(payload).hexdigest()
        digest = f"sha256:{hexadecimal}"
        target_directory = self._objects_root / hexadecimal[:2]
        target_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_directory.chmod(0o700)
        target = target_directory / hexadecimal
        temporary = self._temporary_root / f"{uuid.uuid4().hex}.partial"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            if target.exists():
                self._verify_path(target, digest, len(payload))
                temporary.unlink()
            else:
                os.replace(temporary, target)
                self._fsync_directory(target_directory)
            return CheckpointObject(
                content_reference=f"native-checkpoint://sha256/{hexadecimal}",
                digest=digest,
                size_bytes=len(payload),
                path=target,
            )
        finally:
            temporary.unlink(missing_ok=True)

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
