"""Utility helpers: path encoding, project discovery, interactive selection."""

from __future__ import annotations

import json
import logging
import re
import zlib
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from claude_clean.models import ClaudeDataPaths

logger = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_claude_paths(home: Path | None = None) -> ClaudeDataPaths:
    """Build all Claude data paths from a home directory.

    Args:
        home: Override for testing. Defaults to ``Path.home()``.
    """
    h = home or Path.home()
    claude_dir = h / ".claude"
    return ClaudeDataPaths(
        home=h,
        claude_json=h / ".claude.json",
        claude_dir=claude_dir,
        history_jsonl=claude_dir / "history.jsonl",
        projects_dir=claude_dir / "projects",
        file_history_dir=claude_dir / "file-history",
        session_env_dir=claude_dir / "session-env",
        plans_dir=claude_dir / "plans",
        paste_cache_dir=claude_dir / "paste-cache",
    )


def encode_project_path(absolute_path: str) -> str:
    """Encode an absolute project path for use as a directory name.

    Replicates the JavaScript reference implementation::

        path.replace(/[^a-zA-Z0-9]/g, "-")

    All non-alphanumeric characters (``/``, ``\\``, ``:``, ``.``, spaces, …)
    are replaced with hyphens.

    If the encoded result exceeds 200 characters it is truncated to 200
    characters and a deterministic hash suffix is appended (hyphen +
    ``abs(crc32(path))`` in base-36).

    Note:
        The hash function used here is ``zlib.crc32``.  Claude Code's internal
        implementation may use a different hash; the CRC32 choice is documented
        as a known, intentional divergence.
    """
    encoded = re.sub(r"[^a-zA-Z0-9]", "-", absolute_path)
    if len(encoded) <= 200:
        return encoded
    hash_val = abs(zlib.crc32(absolute_path.encode()))
    suffix = _int_to_base36(hash_val)
    return f"{encoded[:200]}-{suffix}"


def _int_to_base36(n: int) -> str:
    """Convert a non-negative integer to a base-36 string."""
    if n == 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    parts: list[str] = []
    while n:
        n, rem = divmod(n, 36)
        parts.append(chars[rem])
    return "".join(reversed(parts))


# ---------------------------------------------------------------------------
# Project discovery & selection
# ---------------------------------------------------------------------------


def load_projects(paths: ClaudeDataPaths) -> dict[str, Any]:
    """Read ``~/.claude.json`` and return the ``"projects"`` dict.

    Exits with code 1 if the file is missing or malformed.
    """
    if not paths.claude_json.exists():
        typer.echo(
            typer.style(
                f"Claude state file not found: {paths.claude_json}",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1)

    try:
        data = json.loads(paths.claude_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        typer.echo(
            typer.style(
                f"Failed to read {paths.claude_json}: {exc}",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc

    projects: dict[str, Any] = data.get("projects", {})
    if not isinstance(projects, dict):
        typer.echo(
            typer.style(
                f"Unexpected 'projects' value in {paths.claude_json}",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1)

    return projects


def select_projects_interactive(project_keys: list[str]) -> list[str]:
    """Display a numbered list and prompt the user to pick one project or ALL.

    Returns a list with either one path or all paths.
    """
    if not project_keys:
        typer.echo("No projects found in Claude state file.")
        raise typer.Exit(0)

    table = Table(title="Known Projects", show_lines=False)
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Project Path", style="white")

    for idx, path in enumerate(project_keys, start=1):
        table.add_row(str(idx), path)
    all_num = len(project_keys) + 1
    table.add_row(str(all_num), "[bold yellow]ALL[/bold yellow]")

    console.print(table)

    while True:
        raw = typer.prompt(f"Select a project (1-{all_num})")
        try:
            choice = int(raw)
        except ValueError:
            typer.echo(f"Please enter a number between 1 and {all_num}.")
            continue
        if choice == all_num:
            return project_keys
        if 1 <= choice <= len(project_keys):
            return [project_keys[choice - 1]]
        typer.echo(f"Please enter a number between 1 and {all_num}.")


def resolve_projects(
    project: str | None,
    all_flag: bool,
    paths: ClaudeDataPaths,
) -> list[str]:
    """Resolve project selection from CLI flags or interactive prompt.

    Args:
        project: Value of ``--project / -p`` (single path).
        all_flag: Whether ``--all / -a`` was passed.
        paths: Resolved Claude data paths.

    Returns:
        List of selected project path strings.
    """
    projects = load_projects(paths)
    project_keys = sorted(projects.keys())

    if not project_keys:
        typer.echo("No projects found in Claude state file.")
        raise typer.Exit(0)

    if all_flag:
        return project_keys

    if project is not None:
        if project not in projects:
            typer.echo(
                typer.style(
                    f"Project not found in {paths.claude_json}: {project}",
                    fg=typer.colors.RED,
                ),
                err=True,
            )
            typer.echo("Known projects:")
            for key in project_keys:
                typer.echo(f"  {key}")
            raise typer.Exit(1)
        return [project]

    return select_projects_interactive(project_keys)


# ---------------------------------------------------------------------------
# Scope selection
# ---------------------------------------------------------------------------

VALID_SCOPES = ("project", "user", "all")


def select_scope_interactive() -> str:
    """Prompt the user to choose a settings scope.

    Returns:
        One of ``"project"``, ``"user"``, or ``"all"``.
    """
    typer.echo("Settings scope:")
    typer.echo("  1) project — delete {project}/.claude/ directory")
    typer.echo("  2) user    — remove project entry from ~/.claude.json")
    typer.echo("  3) all     — both of the above")

    while True:
        raw = typer.prompt("Select scope (1-3)")
        try:
            choice = int(raw)
        except ValueError:
            typer.echo("Please enter 1, 2, or 3.")
            continue
        if choice in (1, 2, 3):
            return VALID_SCOPES[choice - 1]
        typer.echo("Please enter 1, 2, or 3.")
