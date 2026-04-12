from __future__ import annotations

import json
from pathlib import Path

from tellme.state import ProjectState


def test_state_manifest_includes_feedback_loop_sections(tmp_path: Path) -> None:
    state = ProjectState.create(tmp_path / "state")

    assert state.outputs() == {}
    assert state.syntheses() == {}
    assert state.health_findings() == {}


def test_state_normalizes_existing_manifest_with_feedback_loop_sections(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": {},
                "pages": {},
                "links": {},
                "indexes": {},
                "nodes": {},
                "claims": {},
                "relations": {},
                "conflicts": {},
            }
        ),
        encoding="utf-8",
    )

    state = ProjectState.load(state_dir)

    assert state.outputs() == {}
    assert state.syntheses() == {}
    assert state.health_findings() == {}
    normalized = json.loads((state_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "outputs" in normalized
    assert "syntheses" in normalized
    assert "health_findings" in normalized


def test_state_upserts_feedback_loop_records_with_provenance(tmp_path: Path) -> None:
    state = ProjectState.create(tmp_path / "state")

    state.upsert_output(
        {
            "id": "output:query-alpha",
            "kind": "query_answer",
            "title": "Query Alpha",
            "status": "staged",
            "sources": ["wiki/concepts/alpha.md"],
            "staged_path": "staging/outputs/query-alpha.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )
    state.upsert_synthesis(
        {
            "id": "synthesis:alpha",
            "title": "Alpha Synthesis",
            "status": "staged",
            "sources": ["wiki/concepts/alpha.md"],
            "staged_path": "staging/synthesis/alpha.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )
    state.upsert_health_finding(
        {
            "id": "health:thin-alpha",
            "finding_type": "thin_node",
            "status": "staged",
            "sources": ["wiki/concepts/alpha.md"],
            "staged_path": "staging/health/thin-alpha.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )

    reloaded = ProjectState.load(tmp_path / "state")
    assert reloaded.outputs()["output:query-alpha"]["last_run_id"] == "run-1"
    assert reloaded.syntheses()["synthesis:alpha"]["staged_path"] == "staging/synthesis/alpha.md"
    assert reloaded.health_findings()["health:thin-alpha"]["finding_type"] == "thin_node"
