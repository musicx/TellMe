from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from . import __version__
from .codex import CodexResultError, consume_codex_result, create_codex_handoff
from .compiler import compile_sources
from .config import load_runtime
from .hosts import KNOWN_HOSTS
from .health import create_health_handoff
from .ingest import ingest_file
from .linting import lint_vault
from .project import init_project
from .publish import PublishError, publish_staged_graph
from .query import query_vault
from .reconcile import reconcile_vault
from .resolver import ProjectNotFoundError
from .runs import RunStore
from .workflow import run_workflow


COMMANDS = ("init", "ingest", "compile", "query", "lint", "reconcile", "publish")


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

    lint_parser = subparsers.add_parser("lint", help="Run static vault checks")
    lint_parser.add_argument(
        "--health-handoff",
        action="store_true",
        help="Create an LLM-readable health reflection task instead of running static lint",
    )
    lint_parser.set_defaults(handler=_handle_lint)

    reconcile_parser = subparsers.add_parser("reconcile", help="Reconcile vault drift into state")
    reconcile_parser.set_defaults(handler=_handle_reconcile)

    publish_parser = subparsers.add_parser("publish", help="Publish reviewed staged graph pages to vault")
    publish_target = publish_parser.add_mutually_exclusive_group(required=True)
    publish_target.add_argument("--all", action="store_true", help="Publish all staged graph node pages")
    publish_target.add_argument("--path", help="Publish one staged graph page path")
    publish_parser.set_defaults(handler=_handle_publish)

    compile_parser = subparsers.add_parser("compile", help="Compile registered sources into vault pages")
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
    compile_parser.set_defaults(handler=_handle_compile)

    query_parser = subparsers.add_parser("query", help="Query published vault content")
    query_parser.add_argument("question")
    query_parser.add_argument(
        "--stage",
        action="store_true",
        help="Write a reviewable query answer candidate under staging/queries/",
    )
    query_parser.set_defaults(handler=_handle_query)

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

    run = run_workflow(
        project_root=runtime.project_root,
        runs=runs,
        command="lint",
        host=args.host,
        inputs={},
        operation=operation,
    )
    issues = run.outputs.get("issues", [])
    if args.health_handoff:
        print("tellme lint: health task")
        print(run.outputs["task_markdown_path"])
        print("tellme lint: result template")
        print(run.outputs["result_template_path"])
        return 0
    if not issues:
        print(f"tellme lint: no issues in {runtime.vault_dir}")
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
    except PublishError as exc:
        print(str(exc), file=sys.stderr)
        return 2

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
            result = create_codex_handoff(runtime=runtime, run_id=run.run_id)
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
    except CodexResultError as exc:
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    return int(args.handler(args))
