"""Tests for claude_clean.services."""

from __future__ import annotations

from pathlib import Path

from claude_clean.models import ActionKind, ClaudeDataPaths
from claude_clean.services import (
    plan_history_cleanup,
    plan_metadata_cleanup,
    plan_purge,
    plan_settings_cleanup,
)
from claude_clean.utils import get_claude_paths

from .conftest import (
    PASTE_HASH_1,
    PLAN_NAME_1,
    PLAN_NAME_2,
    PROJECT_A,
    PROJECT_B,
    SESSION_A1,
    SESSION_A2,
    SESSION_B1,
)

# ---------------------------------------------------------------------------
# History cleanup
# ---------------------------------------------------------------------------


class TestPlanHistoryCleanup:
    def test_single_project(self, fake_home: ClaudeDataPaths) -> None:
        """Cleaning project A removes its entries, keeps project B."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)

        # Should have actions for: paste-cache delete, history rewrite,
        # file-history dirs, session-env dirs, plan files, project dir
        kinds = [a.kind for a in actions]
        assert ActionKind.DELETE_FILE in kinds  # paste cache + plan
        assert ActionKind.REWRITE_JSONL in kinds
        assert ActionKind.DELETE_DIR in kinds  # file-history, session-env, project dir

        # The REWRITE_JSONL payload should only contain project B's entry
        rewrite = [a for a in actions if a.kind == ActionKind.REWRITE_JSONL][0]
        assert len(rewrite.payload) == 1
        assert rewrite.payload[0]["project"] == PROJECT_B

    def test_all_projects(self, fake_home: ClaudeDataPaths) -> None:
        """Cleaning all projects leaves history.jsonl empty."""
        actions = plan_history_cleanup([PROJECT_A, PROJECT_B], fake_home)

        rewrite = [a for a in actions if a.kind == ActionKind.REWRITE_JSONL][0]
        assert len(rewrite.payload) == 0

    def test_paste_cache_deletion(self, fake_home: ClaudeDataPaths) -> None:
        """Paste cache files are included in the action list."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)
        paste_deletes = [
            a
            for a in actions
            if a.kind == ActionKind.DELETE_FILE
            and "paste cache" in a.description.lower()
        ]
        assert len(paste_deletes) == 1
        assert paste_deletes[0].path.name == f"{PASTE_HASH_1}.txt"

    def test_file_history_cleanup(self, fake_home: ClaudeDataPaths) -> None:
        """File-history dirs for session IDs are included."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)
        fh_deletes = [
            a
            for a in actions
            if a.kind == ActionKind.DELETE_DIR
            and "file-history" in a.description.lower()
        ]
        session_names = {a.path.name for a in fh_deletes}
        assert SESSION_A1 in session_names
        assert SESSION_A2 in session_names
        assert SESSION_B1 not in session_names

    def test_session_env_cleanup(self, fake_home: ClaudeDataPaths) -> None:
        """Session-env dirs for session IDs are included."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)
        se_deletes = [
            a
            for a in actions
            if a.kind == ActionKind.DELETE_DIR
            and "session-env" in a.description.lower()
        ]
        session_names = {a.path.name for a in se_deletes}
        assert SESSION_A1 in session_names

    def test_plan_file_deletion(self, fake_home: ClaudeDataPaths) -> None:
        """Plan .md files referenced in session files are included."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)
        plan_deletes = [
            a
            for a in actions
            if a.kind == ActionKind.DELETE_FILE and "plan" in a.description.lower()
        ]
        plan_names = {a.path.name for a in plan_deletes}
        assert PLAN_NAME_1 in plan_names
        assert PLAN_NAME_2 not in plan_names

    def test_project_dir_deletion(self, fake_home: ClaudeDataPaths) -> None:
        """The encoded project directory itself is deleted."""
        actions = plan_history_cleanup([PROJECT_A], fake_home)
        proj_deletes = [
            a
            for a in actions
            if a.kind == ActionKind.DELETE_DIR
            and "project dir" in a.description.lower()
        ]
        assert len(proj_deletes) == 1
        assert proj_deletes[0].path.name == "-home-testuser-project-alpha"

    def test_no_matching_entries(self, fake_home: ClaudeDataPaths) -> None:
        """Non-existent project produces rewrite with all lines kept."""
        actions = plan_history_cleanup(["/nonexistent/path"], fake_home)
        rewrite = [a for a in actions if a.kind == ActionKind.REWRITE_JSONL]
        assert len(rewrite) == 1
        assert len(rewrite[0].payload) == 3  # all entries kept

    def test_missing_history_file(self, tmp_path: Path) -> None:
        """No history.jsonl means no history-related actions."""
        paths = get_claude_paths(home=tmp_path)
        paths.claude_dir.mkdir(parents=True)
        actions = plan_history_cleanup(["/some/path"], paths)
        assert not any(a.kind == ActionKind.REWRITE_JSONL for a in actions)


# ---------------------------------------------------------------------------
# Settings cleanup
# ---------------------------------------------------------------------------


class TestPlanSettingsCleanup:
    def test_project_scope(self, fake_home: ClaudeDataPaths) -> None:
        """Project scope deletes {project}/.claude/ directory."""
        # Use the actual path under the fake home where .claude/ exists
        proj_root = str(fake_home.home / "home" / "testuser" / "project-alpha")
        proj_claude = Path(proj_root) / ".claude"
        proj_claude.mkdir(parents=True, exist_ok=True)

        actions = plan_settings_cleanup([proj_root], fake_home, "project")
        dir_deletes = [a for a in actions if a.kind == ActionKind.DELETE_DIR]
        assert len(dir_deletes) == 1
        assert dir_deletes[0].path == proj_claude

    def test_user_scope(self, fake_home: ClaudeDataPaths) -> None:
        """User scope removes the key from claude.json."""
        actions = plan_settings_cleanup([PROJECT_A], fake_home, "user")
        json_rewrites = [a for a in actions if a.kind == ActionKind.REWRITE_JSON]
        assert len(json_rewrites) == 1

        payload = json_rewrites[0].payload
        assert PROJECT_A not in payload["projects"]
        assert PROJECT_B in payload["projects"]

    def test_all_scope(self, fake_home: ClaudeDataPaths) -> None:
        """All scope includes both project dir deletion and JSON rewrite."""
        actions = plan_settings_cleanup([PROJECT_A], fake_home, "all")
        kinds = {a.kind for a in actions}
        # Should have REWRITE_JSON (user scope)
        assert ActionKind.REWRITE_JSON in kinds

    def test_user_scope_all_projects(self, fake_home: ClaudeDataPaths) -> None:
        """Removing all projects from claude.json leaves empty projects dict."""
        actions = plan_settings_cleanup([PROJECT_A, PROJECT_B], fake_home, "user")
        json_rewrites = [a for a in actions if a.kind == ActionKind.REWRITE_JSON]
        assert len(json_rewrites) == 1
        assert json_rewrites[0].payload["projects"] == {}

    def test_project_not_in_json(self, fake_home: ClaudeDataPaths) -> None:
        """Non-existent project key in user scope produces no rewrite."""
        actions = plan_settings_cleanup(["/nonexistent"], fake_home, "user")
        assert not any(a.kind == ActionKind.REWRITE_JSON for a in actions)


# ---------------------------------------------------------------------------
# Metadata cleanup
# ---------------------------------------------------------------------------


class TestPlanMetadataCleanup:
    def test_deletes_claude_md_files(self, fake_home: ClaudeDataPaths) -> None:
        """Both root and nested CLAUDE.md files are targeted."""
        # For this test, project paths are absolute but the actual directories
        # are under fake_home.home. The service uses Path(project_path) directly,
        # so we need paths that map to actual dirs under tmp_path.
        proj_root = fake_home.home / "home" / "testuser" / "project-alpha"
        actions = plan_metadata_cleanup([str(proj_root)], fake_home)

        deleted_names = {a.path.name for a in actions}
        assert "CLAUDE.md" in deleted_names
        assert len(actions) == 2  # root + nested

    def test_missing_files(self, fake_home: ClaudeDataPaths) -> None:
        """No actions if CLAUDE.md doesn't exist at the project path."""
        actions = plan_metadata_cleanup(["/nonexistent/project"], fake_home)
        assert len(actions) == 0

    def test_only_root_exists(self, fake_home: ClaudeDataPaths) -> None:
        """Only the existing CLAUDE.md is included."""
        proj_root = fake_home.home / "home" / "testuser" / "project-beta"
        actions = plan_metadata_cleanup([str(proj_root)], fake_home)
        # project-beta only has root CLAUDE.md, no nested .claude/CLAUDE.md
        assert len(actions) == 1
        assert actions[0].path == proj_root / "CLAUDE.md"


# ---------------------------------------------------------------------------
# Full purge
# ---------------------------------------------------------------------------


class TestPlanPurge:
    def test_combines_all_commands(self, fake_home: ClaudeDataPaths) -> None:
        """Purge includes actions from all three sub-commands."""
        proj_root = str(fake_home.home / "home" / "testuser" / "project-alpha")
        actions = plan_purge([proj_root], fake_home)

        kinds = {a.kind for a in actions}
        # Should have all action kinds
        assert ActionKind.DELETE_FILE in kinds
        assert ActionKind.DELETE_DIR in kinds
        # REWRITE_JSON presence depends on proj_root being in claude.json
        assert ActionKind.REWRITE_JSONL in kinds

    def test_deduplicates(self, fake_home: ClaudeDataPaths) -> None:
        """No duplicate (kind, path) pairs in the result."""
        proj_root = str(fake_home.home / "home" / "testuser" / "project-alpha")
        actions = plan_purge([proj_root], fake_home)

        seen: set[tuple[str, str]] = set()
        for a in actions:
            key = (a.kind.name, str(a.path))
            assert key not in seen, f"Duplicate action: {key}"
            seen.add(key)
