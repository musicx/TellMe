from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.state import ProjectState, StateFormatError


def test_created_manifest_has_versioned_schema_sections(tmp_path: Path) -> None:
    state = ProjectState.create(tmp_path / "state")

    payload = json.loads(state.manifest_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["sources"] == {}
    assert payload["pages"] == {}
    assert payload["links"] == {}
    assert payload["indexes"] == {}


def test_load_migrates_legacy_manifest_version_key(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "sources": {}, "pages": {}}),
        encoding="utf-8",
    )

    state = ProjectState.load(state_dir)

    payload = json.loads(state.manifest_path.read_text(encoding="utf-8"))
    assert state.schema_version == 1
    assert payload["schema_version"] == 1
    assert "version" not in payload
    assert payload["links"] == {}
    assert payload["indexes"] == {}


def test_load_invalid_manifest_fails_with_state_format_error(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "manifest.json").write_text("[]", encoding="utf-8")

    with pytest.raises(StateFormatError):
        ProjectState.load(state_dir)
