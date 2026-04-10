from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LockAlreadyHeldError(RuntimeError):
    """Raised when a local TellMe project lock already exists."""


class ProjectLock:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.lock_path = project_root / ".tellme.lock"

    @contextmanager
    def acquire(self, run_id: str) -> Iterator[None]:
        try:
            handle = self.lock_path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            holder = self.lock_path.read_text(encoding="utf-8").strip()
            raise LockAlreadyHeldError(f"TellMe project lock is already held by {holder}") from exc

        try:
            handle.write(run_id)
            handle.close()
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)
