"""Typer CLI application for claude-clean."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from claude_clean.models import Action, ActionKind
from claude_clean.services import (
    plan_history_cleanup,
    plan_metadata_cleanup,
    plan_purge,
    plan_settings_cleanup,
)
from claude_clean.utils import (
    VALID_SCOPES,
    get_claude_paths,
    resolve_projects,
    select_scope_interactive,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="claude-clean",
    help="Selectively purge Claude Code project data.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Shared option types
# ---------------------------------------------------------------------------

ProjectOpt = Annotated[
    str | None,
    typer.Option("--project", "-p", help="Target a specific project path."),
]
AllOpt = Annotated[
    bool,
    typer.Option("--all", "-a", help="Target all known projects."),
]
DryRunOpt = Annotated[
    bool,
    typer.Option("--dry-run", help="Preview actions without performing them."),
]
YesOpt = Annotated[
    bool,
    typer.Option("--yes", "-y", help="Skip confirmation prompt."),
]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def history(
    project: ProjectOpt = None,
    all_projects: AllOpt = False,
    dry_run: DryRunOpt = False,
    yes: YesOpt = False,
) -> None:
    """Delete conversation history for selected project(s)."""
    paths = get_claude_paths()
    selected = resolve_projects(project, all_projects, paths)
    actions = plan_history_cleanup(selected, paths)
    _execute(actions, dry_run, yes)


@app.command()
def settings(
    project: ProjectOpt = None,
    all_projects: AllOpt = False,
    scope: Annotated[
        str | None,
        typer.Option(
            "--scope",
            "-s",
            help="Scope: project, user, or all.",
        ),
    ] = None,
    dry_run: DryRunOpt = False,
    yes: YesOpt = False,
) -> None:
    """Delete project settings (project-scope, user-scope, or both)."""
    if scope is not None and scope not in VALID_SCOPES:
        typer.echo(
            typer.style(
                f"Invalid scope '{scope}'. Must be one of: {', '.join(VALID_SCOPES)}",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1)

    resolved_scope = scope if scope is not None else select_scope_interactive()

    paths = get_claude_paths()
    selected = resolve_projects(project, all_projects, paths)
    actions = plan_settings_cleanup(selected, paths, resolved_scope)
    _execute(actions, dry_run, yes)


@app.command()
def metadata(
    project: ProjectOpt = None,
    all_projects: AllOpt = False,
    dry_run: DryRunOpt = False,
    yes: YesOpt = False,
) -> None:
    """Delete project metadata (CLAUDE.md memory files)."""
    paths = get_claude_paths()
    selected = resolve_projects(project, all_projects, paths)
    actions = plan_metadata_cleanup(selected, paths)
    _execute(actions, dry_run, yes)


@app.command()
def purge(
    project: ProjectOpt = None,
    all_projects: AllOpt = False,
    dry_run: DryRunOpt = False,
    yes: YesOpt = False,
) -> None:
    """Run full cleanup: history + settings (all) + metadata."""
    paths = get_claude_paths()
    selected = resolve_projects(project, all_projects, paths)
    actions = plan_purge(selected, paths)
    _execute(actions, dry_run, yes)


# ---------------------------------------------------------------------------
# Execution engine
# ---------------------------------------------------------------------------


def _execute(actions: list[Action], dry_run: bool, yes: bool) -> None:
    """Display planned actions, optionally confirm, then execute."""
    if not actions:
        typer.echo("Nothing to do.")
        raise typer.Exit(0)

    for action in actions:
        prefix = "[DRY RUN] " if dry_run else ""
        typer.echo(f"  {prefix}{action.description}")

    if dry_run:
        raise typer.Exit(0)

    if not yes:
        typer.confirm("\nProceed?", abort=True)

    for action in actions:
        _run_action(action)

    typer.echo(f"\nDone. {len(actions)} action(s) completed.")


def _run_action(action: Action) -> None:
    """Execute a single planned action."""
    match action.kind:
        case ActionKind.DELETE_FILE:
            action.path.unlink(missing_ok=True)
            logger.info("Deleted file: %s", action.path)
        case ActionKind.DELETE_DIR:
            shutil.rmtree(action.path, ignore_errors=True)
            logger.info("Deleted directory: %s", action.path)
        case ActionKind.REWRITE_JSON:
            content = json.dumps(action.payload, indent=2) + "\n"
            _atomic_write(action.path, content)
            logger.info("Rewrote JSON: %s", action.path)
        case ActionKind.REWRITE_JSONL:
            lines: list[str] = []
            for entry in action.payload:
                if "_raw" in entry:
                    lines.append(entry["_raw"])
                else:
                    lines.append(json.dumps(entry))
            content = "\n".join(lines) + "\n" if lines else ""
            _atomic_write(action.path, content)
            logger.info("Rewrote JSONL: %s", action.path)


def _atomic_write(target: Path, content: str) -> None:
    """Write *content* to *target* atomically.

    Creates a temporary file in the same directory, writes content,
    then uses ``os.replace()`` to atomically swap.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1  # Mark as closed
        os.replace(tmp_path, target)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        raise
