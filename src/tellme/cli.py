from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from . import __version__
from .compiler import compile_sources
from .config import load_runtime
from .hosts import KNOWN_HOSTS
from .ingest import ingest_file
from .linting import lint_vault
from .project import init_project
from .query import query_vault
from .reconcile import reconcile_vault
from .resolver import ProjectNotFoundError
from .runs import RunStore
from .workflow import run_workflow


COMMANDS = ("init", "ingest", "compile", "query", "lint", "reconcile")


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
    lint_parser.set_defaults(handler=_handle_lint)

    reconcile_parser = subparsers.add_parser("reconcile", help="Reconcile vault drift into state")
    reconcile_parser.set_defaults(handler=_handle_reconcile)

    compile_parser = subparsers.add_parser("compile", help="Compile registered sources into vault pages")
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


def _handle_compile(args: argparse.Namespace) -> int:
    runtime = _load_runtime_from_args(args)
    if runtime is None:
        return 2
    runs = RunStore(runtime.runs_dir)

    def operation(run):
        result = compile_sources(runtime=runtime, run_id=run.run_id, host=args.host)
        return {
            "published_pages": result.published_pages,
            "staged_pages": result.staged_pages,
            "host_task_path": result.host_task_path,
            "artifact_path": result.artifact_path,
        }

    run = run_workflow(
        project_root=runtime.project_root,
        runs=runs,
        command="compile",
        host=args.host,
        inputs={},
        operation=operation,
    )
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
