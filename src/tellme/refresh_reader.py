from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .codex import consume_codex_result, create_codex_handoff
from .config import ProjectRuntime
from .linting import LintResult, lint_vault
from .publish import PublishResult, publish_staged_graph
from .reader_rewrite import consume_reader_rewrite_result, create_reader_rewrite_handoff


@dataclass(frozen=True)
class RefreshReaderPrepareResult:
    graph_task_markdown_path: str
    graph_result_template_path: str


@dataclass(frozen=True)
class RefreshReaderConsumeGraphResult:
    consumed_graph_path: str
    graph_staged_pages: list[str]
    published_pages: list[str]
    rewrite_task_markdown_path: str
    rewrite_result_template_path: str


@dataclass(frozen=True)
class RefreshReaderConsumeRewriteResult:
    consumed_rewrite_path: str
    rewrite_staged_pages: list[str]
    published_pages: list[str]
    lint_result: LintResult


def prepare_refresh_reader(
    runtime: ProjectRuntime,
    run_id: str,
    health_finding_id: str | None = None,
) -> RefreshReaderPrepareResult:
    result = create_codex_handoff(
        runtime=runtime,
        run_id=run_id,
        health_finding_id=health_finding_id,
    )
    return RefreshReaderPrepareResult(
        graph_task_markdown_path=result.task_markdown_path,
        graph_result_template_path=result.result_template_path,
    )


def consume_graph_result_for_reader_refresh(
    runtime: ProjectRuntime,
    run_id: str,
    host: str,
    result_path: Path,
) -> RefreshReaderConsumeGraphResult:
    graph_result = consume_codex_result(
        runtime=runtime,
        result_path=result_path,
        consume_run_id=run_id,
    )
    publish_result = publish_staged_graph(runtime=runtime, run_id=run_id, host=host)
    rewrite_result = create_reader_rewrite_handoff(runtime=runtime, run_id=run_id, host=host)
    return RefreshReaderConsumeGraphResult(
        consumed_graph_path=graph_result.staged_page,
        graph_staged_pages=graph_result.staged_pages,
        published_pages=publish_result.published_pages,
        rewrite_task_markdown_path=rewrite_result.task_markdown_path,
        rewrite_result_template_path=rewrite_result.result_template_path,
    )


def consume_reader_rewrite_for_refresh(
    runtime: ProjectRuntime,
    run_id: str,
    host: str,
    result_path: Path,
) -> RefreshReaderConsumeRewriteResult:
    rewrite_result = consume_reader_rewrite_result(
        runtime=runtime,
        result_path=result_path,
        consume_run_id=run_id,
    )
    publish_result = publish_staged_graph(runtime=runtime, run_id=run_id, host=host)
    lint_result = lint_vault(runtime=runtime, current_run_id=run_id)
    return RefreshReaderConsumeRewriteResult(
        consumed_rewrite_path=rewrite_result.result_path,
        rewrite_staged_pages=rewrite_result.staged_pages,
        published_pages=publish_result.published_pages,
        lint_result=lint_result,
    )
