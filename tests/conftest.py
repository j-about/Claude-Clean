"""Shared test fixtures for claude-clean tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from claude_clean.models import ClaudeDataPaths
from claude_clean.utils import get_claude_paths

# ---------------------------------------------------------------------------
# Sample data constants
# ---------------------------------------------------------------------------

PROJECT_A = "/home/testuser/project-alpha"
PROJECT_B = "/home/testuser/project-beta"
PROJECT_WIN = "C:\\Users\\testuser\\project-gamma"

SESSION_A1 = "aaaa1111-0000-0000-0000-000000000001"
SESSION_A2 = "aaaa1111-0000-0000-0000-000000000002"
SESSION_B1 = "bbbb2222-0000-0000-0000-000000000001"

PASTE_HASH_1 = "abcdef1234567890"
PASTE_HASH_2 = "1234567890abcdef"

PLAN_NAME_1 = "elegant-dreaming-otter.md"
PLAN_NAME_2 = "fizzy-herding-ember.md"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _build_claude_json(projects: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal ~/.claude.json structure."""
    return {
        "numStartups": 10,
        "projects": projects,
    }


def _build_history_lines(
    entries: list[dict[str, Any]],
) -> str:
    """Serialize history entries as JSONL text."""
    return "\n".join(json.dumps(e) for e in entries) + "\n"


# ---------------------------------------------------------------------------
# Main fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_home(tmp_path: Path) -> ClaudeDataPaths:
    """Create a realistic Claude Code data tree under *tmp_path*.

    Populates:
    - claude.json with PROJECT_A and PROJECT_B
    - history.jsonl with entries across both projects (and paste hashes)
    - projects/ with encoded dirs containing session files and UUID subdirs
    - file-history/ and session-env/ with session subdirs
    - plans/ with plan files
    - paste-cache/ with cached paste files
    - CLAUDE.md files at project roots
    """
    paths = get_claude_paths(home=tmp_path)

    # --- ~/.claude.json ---
    claude_json_data = _build_claude_json(
        {
            PROJECT_A: {"allowedTools": [], "lastSessionId": SESSION_A2},
            PROJECT_B: {"allowedTools": [], "lastSessionId": SESSION_B1},
        }
    )
    paths.claude_json.write_text(
        json.dumps(claude_json_data, indent=2), encoding="utf-8"
    )

    # --- ~/.claude/ directory tree ---
    paths.claude_dir.mkdir(parents=True, exist_ok=True)

    # history.jsonl
    history_entries = [
        {
            "display": "hello from A",
            "pastedContents": {PASTE_HASH_1: {"size": 100}},
            "timestamp": 1700000001000,
            "project": PROJECT_A,
            "sessionId": SESSION_A1,
        },
        {
            "display": "another from A",
            "pastedContents": {},
            "timestamp": 1700000002000,
            "project": PROJECT_A,
            "sessionId": SESSION_A2,
        },
        {
            "display": "hello from B",
            "pastedContents": {PASTE_HASH_2: {"size": 200}},
            "timestamp": 1700000003000,
            "project": PROJECT_B,
            "sessionId": SESSION_B1,
        },
    ]
    paths.history_jsonl.write_text(
        _build_history_lines(history_entries), encoding="utf-8"
    )

    # projects/ — encoded project directories
    encoded_a = "-home-testuser-project-alpha"
    encoded_b = "-home-testuser-project-beta"

    proj_dir_a = paths.projects_dir / encoded_a
    proj_dir_b = paths.projects_dir / encoded_b
    proj_dir_a.mkdir(parents=True)
    proj_dir_b.mkdir(parents=True)

    # Session subdirectories (treated as session IDs)
    (proj_dir_a / SESSION_A1).mkdir()
    (proj_dir_a / SESSION_A2).mkdir()
    (proj_dir_b / SESSION_B1).mkdir()

    # Session files with plan references
    session_file_a = proj_dir_a / f"{SESSION_A1}.jsonl"
    session_file_a.write_text(
        f'{{"type":"plan","file":"{PLAN_NAME_1}"}}\n',
        encoding="utf-8",
    )

    session_file_b = proj_dir_b / f"{SESSION_B1}.jsonl"
    session_file_b.write_text(
        f'{{"type":"plan","file":"{PLAN_NAME_2}"}}\n',
        encoding="utf-8",
    )

    # file-history/
    (paths.file_history_dir / SESSION_A1).mkdir(parents=True)
    (paths.file_history_dir / SESSION_A2).mkdir(parents=True)
    (paths.file_history_dir / SESSION_B1).mkdir(parents=True)
    # Add a dummy file so rmtree has something to delete
    (paths.file_history_dir / SESSION_A1 / "snapshot.txt").write_text("data")

    # session-env/
    (paths.session_env_dir / SESSION_A1).mkdir(parents=True)
    (paths.session_env_dir / SESSION_B1).mkdir(parents=True)

    # plans/
    paths.plans_dir.mkdir(parents=True)
    (paths.plans_dir / PLAN_NAME_1).write_text("# Plan 1\n")
    (paths.plans_dir / PLAN_NAME_2).write_text("# Plan 2\n")

    # paste-cache/
    paths.paste_cache_dir.mkdir(parents=True)
    (paths.paste_cache_dir / f"{PASTE_HASH_1}.txt").write_text("pasted content 1")
    (paths.paste_cache_dir / f"{PASTE_HASH_2}.txt").write_text("pasted content 2")

    # Project root directories with CLAUDE.md
    project_a_root = tmp_path / "home" / "testuser" / "project-alpha"
    project_a_root.mkdir(parents=True)
    (project_a_root / "CLAUDE.md").write_text("# Project A memory\n")
    (project_a_root / ".claude").mkdir()
    (project_a_root / ".claude" / "CLAUDE.md").write_text("# Project A nested\n")

    project_b_root = tmp_path / "home" / "testuser" / "project-beta"
    project_b_root.mkdir(parents=True)
    (project_b_root / "CLAUDE.md").write_text("# Project B memory\n")

    return paths
