from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from . import __version__
from .codex import CodexHandoffError, CodexResultError, consume_codex_result, create_codex_handoff
from .compiler import compile_sources
from .config import load_runtime
from .hosts import KNOWN_HOSTS
from .health import (
    HealthResultError,
    consume_health_result,
    create_health_handoff,
    resolve_health_finding,
)
from .ingest import ingest_file
from .linting import lint_vault
from .project import init_project
from .publish import PublishError, publish_staged_graph
from .query import query_vault
from .refresh_reader import (
    consume_graph_result_for_reader_refresh,
    consume_reader_rewrite_for_refresh,
    prepare_refresh_reader,
)
from .reader_rewrite import (
    ReaderRewriteError,
    consume_reader_rewrite_result,
    create_reader_rewrite_handoff,
)
from .reconcile import reconcile_vault
from .resolver import ProjectNotFoundError
from .runs import RunStore
from .workflow import run_workflow


COMMANDS = ("init", "ingest", "compile", "query", "lint", "reconcile", "publish", "refresh-reader")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tellme",
        description="TellMe hybrid LLM-wiki orchestrator.",
    )
    parser.add_argument("--version", action="version", version=f"tellme {__version__}")
    parser.add_argument("--project", help="TellMe project root")
    parser.add_argument("--machine", help="Machine config name")
    parser.add_argument("--host", choices=sorted(KNOWN_HOSTS), default="codex", help="Host identity")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a TellMe project")
    init_parser.add_argument("project_root", nargs="?", default=".")
    init_parser.add_argument(
        "--machine",
        default=platform.node() or "local",
        help="Machine config name to create under config/machines/",
    )
    init_parser.set_defaults(handler=_handle_init)

    ingest_parser = subparsers.add_parser("ingest", help="Register a source file")
    ingest_parser.add_argument("source")
    ingest_parser.set_defaults(handler=_handle_ingest)

    lint_parser = subparsers.add_parser("lint", help="Run static wiki checks")
    lint_mode = lint_parser.add_mutually_exclusive_group()
    lint_mode.add_argument(
        "--health-handoff",
        action="store_true",
        help="Create an LLM-readable health reflection task instead of running static lint",
    )
    lint_mode.add_argument(
        "--consume-health-result",
        help="Consume a staged health reflection result JSON",
    )
    lint_mode.add_argument(
        "--resolve-health-finding",
        help="Mark a staged health finding as resolved",
    )
    lint_parser.set_defaults(handler=_handle_lint)

    reconcile_parser = subparsers.add_parser("reconcile", help="Reconcile wiki drift into state")
    reconcile_parser.set_defaults(handler=_handle_reconcile)

    publish_parser = subparsers.add_parser("publish", help="Publish reviewed staged graph pages to wiki")
    publish_target = publish_parser.add_mutually_exclusive_group(required=True)
    publish_target.add_argument("--all", action="store_true", help="Publish all staged graph node pages")
    publish_target.add_argument("--path", help="Publish one staged graph page path")
    publish_target.add_argument(
        "--reader-rewrite-handoff",
        action="store_true",
        help="Create a reader rewrite handoff task for a host",
    )
    publish_target.add_argument(
        "--consume-reader-rewrite",
        help="Consume a staged reader rewrite result JSON",
    )
    publish_parser.set_defaults(handler=_handle_publish)

    compile_parser = subparsers.add_parser("compile", help="Compile registered sources into wiki pages")
    compile_mode = compile_parser.add_mutually_exclusive_group()
    compile_mode.add_argument(
        "--handoff",
        action="store_true",
        help="Create a Codex-readable compile task without local compile output",
    )
    compile_mode.add_argument(
        "--consume-result",
        help="Consume a Codex result JSON and register its staged output",
    )
    compile_parser.add_argument(
        "--health-finding",
        help="Focus a Codex handoff on one staged health finding id",
    )
    compile_parser.set_defaults(handler=_handle_compile)

    query_parser = subparsers.add_parser("query", help="Query published wiki content")
    query_parser.add_argument("question")
    query_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write a reviewable query answer candidate under staging/queries/",
    )
    query_parser.set_defaults(handler=_handle_query)

    refresh_parser = subparsers.add_parser(
        "refresh-reader",
        help="Run the staged reader refresh workflow",
    )
    refresh_mode = refresh_parser.add_mutually_exclusive_group()
    refresh_mode.add_argument(
        "--consume-graph-result",
        help="Consume a Codex graph result JSON, publish it, and generate a reader rewrite handoff",
    )
    refresh_mode.add_argument(
        "--consume-reader-rewrite",
        help="Consume a reader rewrite result JSON, publish it, and run lint",
    )
    refresh_parser.add_argument(
        "--health-finding",
        help="Focus the graph handoff on one staged health finding id",
    )
    refresh_parser.set_defaults(handler=_handle_refresh_reader)

    return parser


def _handle_init(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    init_project(project_root=project_root, machine=args.machine)
    print(f"TellMe project initialized at {project_root}")
    return 0


def _load_runtime_from_args(args: argparse.Namespace):
    try:
        return load_runtime(
            project_root=Path(args.project).expanduser().resolve() if args.project else None,
            machine=args.machine,
            host=args.host,
        )
    except ProjectNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _handle_ingest(args: argparse.Namespace) -> int:
    try:
        runtime = _load_runtime_from_args(args)
        if runtime is None:
            return 2
        runs = RunStore(runtime.runs_dir)

        def operation(run):
            source = ingest_file(runtime, Path(args.source), run.run_id)
            return {"source": source.path}

        run = run_workflow(
            project_root=runtime.project_root,
            runs=runs,
            command="ingest",
            host=args.host,
            inputs={"source": args.source},
            operation=operation,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"tellme ingest: registered {run.outputs['source']} in {runtime.project_root}")
    return 0


def _handle_lint(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2

    runs = RunStore(runtime.runs_dir)

    def operation(run):
        if args.health_handoff:
            result = create_health_handoff(runtime=runtime, run_id=run.run_id, host=args.host)
            return {
                "task_json_path": result.task_json_path,
                "task_markdown_path": result.task_markdown_path,
                "result_template_path": result.result_template_path,
                "issues": [],
            }
        if args.consume_health_result:
            result_path = Path(args.consume_health_result)
            if not result_path.is_absolute():
                data_result_path = runtime.data_root / result_path
                result_path = data_result_path if data_result_path.exists() else runtime.project_root / result_path
            result = consume_health_result(
                runtime=runtime,
                result_path=result_path,
                consume_run_id=run.run_id,
            )
            return {
                "consumed_result_path": result.result_path,
                "finding_ids": result.finding_ids,
                "staged_pages": result.staged_pages,
                "issues": [],
            }
        if args.resolve_health_finding:
            result = resolve_health_finding(
                runtime=runtime,
                finding_id=args.resolve_health_finding,
                host=args.host,
                run_id=run.run_id,
            )
            return {
                "resolved_finding_id": result.finding_id,
                "issues": [],
            }
        result = lint_vault(runtime, current_run_id=run.run_id)
        return {
            "issues": [
                {
                    "issue_type": issue.issue_type,
                    "path": issue.path,
                    "message": issue.message,
                    "severity": issue.severity,
                }
                for issue in result.issues
            ]
        }

    try:
        run = run_workflow(
            project_root=runtime.project_root,
            runs=runs,
            command="lint",
            host=args.host,
            inputs={},
            operation=operation,
        )
    except HealthResultError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    issues = run.outputs.get("issues", [])
    if args.health_handoff:
        print("tellme lint: health task")
        print(run.outputs["task_markdown_path"])
        print("tellme lint: result template")
        print(run.outputs["result_template_path"])
        return 0
    if args.consume_health_result:
        print(f"tellme lint: consumed health result {run.outputs['consumed_result_path']}")
        for page in run.outputs.get("staged_pages", []):
            print(page)
        return 0
    if args.resolve_health_finding:
        print(f"tellme lint: resolved health finding {run.outputs['resolved_finding_id']}")
        return 0
    if not issues:
        print(f"tellme lint: no issues in {runtime.wiki_dir}")
        return 0
    for issue in issues:
        print(f"{issue['severity']}: {issue['issue_type']}: {issue['path']}: {issue['message']}")
    return 1



def _handle_reconcile(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        result = reconcile_vault(runtime=runtime, run_id=run.run_id, host=args.host)
        return {"changed_pages": result.changed_pages}

    run = run_workflow(
        project_root=runtime.project_root,
        runs=runs,
        command="reconcile",
        host=args.host,
        inputs={},
        operation=operation,
    )

    changed_pages = run.outputs.get("changed_pages", [])
    print(f"tellme reconcile: {len(changed_pages)} changed page(s)")
    return 0


def _handle_publish(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        if args.reader_rewrite_handoff:
            result = create_reader_rewrite_handoff(runtime=runtime, run_id=run.run_id, host=args.host)
            return {
                "task_json_path": result.task_json_path,
                "task_markdown_path": result.task_markdown_path,
                "result_template_path": result.result_template_path,
            }
        if args.consume_reader_rewrite:
            result_path = Path(args.consume_reader_rewrite)
            if not result_path.is_absolute():
                data_result_path = runtime.data_root / result_path
                result_path = data_result_path if data_result_path.exists() else runtime.project_root / result_path
            result = consume_reader_rewrite_result(
                runtime=runtime,
                result_path=result_path,
                consume_run_id=run.run_id,
            )
            return {
                "consumed_rewrite_path": result.result_path,
                "staged_pages": result.staged_pages,
            }
        result = publish_staged_graph(
            runtime=runtime,
            run_id=run.run_id,
            host=args.host,
            staged_path=None if args.all else args.path,
        )
        return {"published_pages": result.published_pages}

    try:
        run = run_workflow(
            project_root=runtime.project_root,
            runs=runs,
            command="publish",
            host=args.host,
            inputs={"all": args.all, "path": args.path},
            operation=operation,
        )
    except (PublishError, ReaderRewriteError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.reader_rewrite_handoff:
        print("tellme publish: reader rewrite task")
        print(run.outputs["task_markdown_path"])
        print("tellme publish: result template")
        print(run.outputs["result_template_path"])
        return 0
    if args.consume_reader_rewrite:
        first_page = run.outputs["staged_pages"][0] if run.outputs.get("staged_pages") else run.outputs["consumed_rewrite_path"]
        print(f"tellme publish: consumed reader rewrite {first_page}")
        return 0
    published_pages = run.outputs.get("published_pages", [])
    print(f"tellme publish: published {len(published_pages)} page(s)")
    for page in published_pages:
        print(page)
    return 0


def _handle_compile(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    if (args.handoff or args.consume_result) and args.host != "codex":
        print("--handoff and --consume-result require --host codex", file=sys.stderr)
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        if args.handoff:
            result = create_codex_handoff(
                runtime=runtime,
                run_id=run.run_id,
                health_finding_id=args.health_finding,
            )
            return {
                "task_json_path": result.task_json_path,
                "task_markdown_path": result.task_markdown_path,
                "result_template_path": result.result_template_path,
                "source_references": result.source_references,
            }
        if args.consume_result:
            result_path = Path(args.consume_result)
            if not result_path.is_absolute():
                data_result_path = runtime.data_root / result_path
                result_path = data_result_path if data_result_path.exists() else runtime.project_root / result_path
            result = consume_codex_result(
                runtime=runtime,
                result_path=result_path,
                consume_run_id=run.run_id,
            )
            return {
                "staged_page": result.staged_page,
                "source_references": result.source_references,
            }
        result = compile_sources(runtime=runtime, run_id=run.run_id, host=args.host)
        return {
            "published_pages": result.published_pages,
            "staged_pages": result.staged_pages,
            "host_task_path": result.host_task_path,
            "artifact_path": result.artifact_path,
        }

    try:
        run = run_workflow(
            project_root=runtime.project_root,
            runs=runs,
            command="compile",
            host=args.host,
            inputs={},
            operation=operation,
        )
    except (CodexResultError, CodexHandoffError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.handoff:
        print("tellme compile: codex task")
        print(run.outputs["task_markdown_path"])
        print("tellme compile: result template")
        print(run.outputs["result_template_path"])
        return 0
    if args.consume_result:
        print(f"tellme compile: consumed codex result {run.outputs['staged_page']}")
        return 0
    published_pages = run.outputs.get("published_pages", [])
    staged_pages = run.outputs.get("staged_pages", [])
    print(f"tellme compile: published {len(published_pages)} page(s)")
    for page in published_pages:
        print(page)
    print(f"tellme compile: staged {len(staged_pages)} page(s)")
    for page in staged_pages:
        print(page)
    return 0


def _handle_query(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        result = query_vault(
            runtime=runtime,
            question=args.question,
            run_id=run.run_id,
            host=args.host,
            stage=args.stage,
        )
        return {
            "answer_path": result.answer_path,
            "matched_pages": result.matched_pages,
            "host_task_path": result.host_task_path,
            "staged_path": result.staged_path,
        }

    run = run_workflow(
        project_root=runtime.project_root,
        runs=runs,
        command="query",
        host=args.host,
        inputs={"question": args.question, "stage": args.stage},
        operation=operation,
    )
    print(f"tellme query: wrote {run.outputs['answer_path']}")
    if run.outputs.get("staged_path"):
        print(f"tellme query: staged {run.outputs['staged_path']}")
    return 0


def _handle_refresh_reader(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    if args.host != "codex":
        print("refresh-reader requires --host codex", file=sys.stderr)
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        if args.consume_graph_result:
            result_path = Path(args.consume_graph_result)
            if not result_path.is_absolute():
                data_result_path = runtime.data_root / result_path
                result_path = data_result_path if data_result_path.exists() else runtime.project_root / result_path
            result = consume_graph_result_for_reader_refresh(
                runtime=runtime,
                run_id=run.run_id,
                host=args.host,
                result_path=result_path,
            )
            return {
                "consumed_graph_path": result.consumed_graph_path,
                "graph_staged_pages": result.graph_staged_pages,
                "published_pages": result.published_pages,
                "rewrite_task_markdown_path": result.rewrite_task_markdown_path,
                "rewrite_result_template_path": result.rewrite_result_template_path,
            }
        if args.consume_reader_rewrite:
            result_path = Path(args.consume_reader_rewrite)
            if not result_path.is_absolute():
                data_result_path = runtime.data_root / result_path
                result_path = data_result_path if data_result_path.exists() else runtime.project_root / result_path
            result = consume_reader_rewrite_for_refresh(
                runtime=runtime,
                run_id=run.run_id,
                host=args.host,
                result_path=result_path,
            )
            return {
                "consumed_rewrite_path": result.consumed_rewrite_path,
                "rewrite_staged_pages": result.rewrite_staged_pages,
                "published_pages": result.published_pages,
                "issues": [
                    {
                        "issue_type": issue.issue_type,
                        "path": issue.path,
                        "message": issue.message,
                        "severity": issue.severity,
                    }
                    for issue in result.lint_result.issues
                ],
            }
        result = prepare_refresh_reader(
            runtime=runtime,
            run_id=run.run_id,
            health_finding_id=args.health_finding,
        )
        return {
            "graph_task_markdown_path": result.graph_task_markdown_path,
            "graph_result_template_path": result.graph_result_template_path,
        }

    try:
        run = run_workflow(
            project_root=runtime.project_root,
            runs=runs,
            command="refresh-reader",
            host=args.host,
            inputs={
                "consume_graph_result": args.consume_graph_result,
                "consume_reader_rewrite": args.consume_reader_rewrite,
                "health_finding": args.health_finding,
            },
            operation=operation,
        )
    except (CodexResultError, CodexHandoffError, PublishError, ReaderRewriteError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.consume_graph_result:
        print(f"tellme refresh-reader: consumed graph result {run.outputs['consumed_graph_path']}")
        print(f"tellme refresh-reader: published {len(run.outputs.get('published_pages', []))} page(s)")
        for page in run.outputs.get("published_pages", []):
            print(page)
        print("tellme refresh-reader: reader rewrite task")
        print(run.outputs["rewrite_task_markdown_path"])
        print("tellme refresh-reader: reader rewrite result template")
        print(run.outputs["rewrite_result_template_path"])
        return 0

    if args.consume_reader_rewrite:
        rewrite_pages = run.outputs.get("rewrite_staged_pages", [])
        first_page = rewrite_pages[0] if rewrite_pages else run.outputs["consumed_rewrite_path"]
        print(f"tellme refresh-reader: consumed reader rewrite {first_page}")
        print(f"tellme refresh-reader: published {len(run.outputs.get('published_pages', []))} page(s)")
        for page in run.outputs.get("published_pages", []):
            print(page)
        issues = run.outputs.get("issues", [])
        if not issues:
            print("tellme refresh-reader: lint clean")
            return 0
        for issue in issues:
            print(f"{issue['severity']}: {issue['issue_type']}: {issue['path']}: {issue['message']}")
        return 1

    print("tellme refresh-reader: graph task")
    print(run.outputs["graph_task_markdown_path"])
    print("tellme refresh-reader: graph result template")
    print(run.outputs["graph_result_template_path"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    return int(args.handler(args))
