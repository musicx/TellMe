from __future__ import annotations

import argparse
import platform
from pathlib import Path

from . import __version__
from .project import init_project


COMMANDS = ("init", "ingest", "compile", "query", "lint", "reconcile")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tellme",
        description="TellMe hybrid LLM-wiki orchestrator.",
    )
    parser.add_argument("--version", action="version", version=f"tellme {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a TellMe project")
    init_parser.add_argument("project_root", nargs="?", default=".")
    init_parser.add_argument(
        "--machine",
        default=platform.node() or "local",
        help="Machine config name to create under config/machines/",
    )
    init_parser.set_defaults(handler=_handle_init)

    for command in COMMANDS[1:]:
        command_parser = subparsers.add_parser(command, help=f"{command} workflow placeholder")
        command_parser.set_defaults(handler=_handle_not_implemented)

    return parser


def _handle_init(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    init_project(project_root=project_root, machine=args.machine)
    print(f"TellMe project initialized at {project_root}")
    return 0


def _handle_not_implemented(args: argparse.Namespace) -> int:
    print(f"tellme {args.command}: command skeleton is present; implementation pending.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    return int(args.handler(args))
