from __future__ import annotations

import shutil
from pathlib import Path

from .config import ProjectRuntime
from .state import ProjectState, SourceRecord


def ingest_file(runtime: ProjectRuntime, source_path: Path, run_id: str) -> SourceRecord:
    source = source_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source file not found: {source}")

    raw_path = _raw_destination(runtime=runtime, source=source)
    if raw_path != source:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, raw_path)

    content = raw_path.read_text(encoding="utf-8")
    record = SourceRecord.register(
        project_root=runtime.project_root,
        path=raw_path,
        content=content,
        registration_run_id=run_id,
    )
    state = ProjectState.load(runtime.state_dir)
    state.upsert_source(record)
    return record


def _raw_destination(runtime: ProjectRuntime, source: Path) -> Path:
    raw_dir = runtime.raw_dir.resolve()
    try:
        source.relative_to(raw_dir)
        return source
    except ValueError:
        pass

    candidate = raw_dir / source.name
    if not candidate.exists():
        return candidate

    stem = source.stem
    suffix = source.suffix
    counter = 1
    while True:
        candidate = raw_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
