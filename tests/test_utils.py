"""Tests for claude_clean.utils."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.exceptions import Exit as ClickExit

from claude_clean.models import ClaudeDataPaths
from claude_clean.utils import (
    _int_to_base36,
    encode_project_path,
    get_claude_paths,
    load_projects,
    resolve_projects,
    select_projects_interactive,
    select_scope_interactive,
)

# ---------------------------------------------------------------------------
# Path encoding
# ---------------------------------------------------------------------------


class TestEncodeProjectPath:
    """Tests for the project path encoding function."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/home/user/project", "-home-user-project"),
            ("/home/user/my-project", "-home-user-my-project"),
            ("/home/user/my.project", "-home-user-my-project"),
            ("/home/user/my project", "-home-user-my-project"),
            ("/", "-"),
            ("/a", "-a"),
        ],
    )
    def test_posix_paths(self, path: str, expected: str) -> None:
        assert encode_project_path(path) == expected

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("C:\\Users\\user\\project", "C--Users-user-project"),
            ("C:\\Users\\user\\my-project", "C--Users-user-my-project"),
            ("D:\\dev\\repo.git", "D--dev-repo-git"),
        ],
    )
    def test_windows_paths(self, path: str, expected: str) -> None:
        assert encode_project_path(path) == expected

    def test_truncation_with_hash(self) -> None:
        """Paths encoding to >200 chars get truncated with a hash suffix."""
        long_path = "/home/user/" + "a" * 250
        encoded = encode_project_path(long_path)

        # Should be truncated: 200 chars + "-" + hash suffix
        assert len(encoded) > 200
        # Verify structure: first 200 chars of full encoding, then hyphen, then base36
        import re

        full_no_trunc = re.sub(r"[^a-zA-Z0-9]", "-", long_path)
        assert encoded.startswith(full_no_trunc[:200] + "-")

    def test_short_path_no_truncation(self) -> None:
        """Paths encoding to <=200 chars have no hash suffix."""
        path = "/home/user/short-project"
        encoded = encode_project_path(path)
        import re

        expected = re.sub(r"[^a-zA-Z0-9]", "-", path)
        assert encoded == expected
        assert len(encoded) <= 200


class TestIntToBase36:
    """Tests for base-36 conversion."""

    def test_zero(self) -> None:
        assert _int_to_base36(0) == "0"

    def test_small_numbers(self) -> None:
        assert _int_to_base36(1) == "1"
        assert _int_to_base36(35) == "z"
        assert _int_to_base36(36) == "10"
        assert _int_to_base36(100) == "2s"


# ---------------------------------------------------------------------------
# get_claude_paths
# ---------------------------------------------------------------------------


class TestGetClaudePaths:
    def test_default_home(self) -> None:
        paths = get_claude_paths()
        assert paths.home == Path.home()
        assert paths.claude_json == Path.home() / ".claude.json"

    def test_custom_home(self, tmp_path: Path) -> None:
        paths = get_claude_paths(home=tmp_path)
        assert paths.home == tmp_path
        assert paths.claude_dir == tmp_path / ".claude"
        assert paths.history_jsonl == tmp_path / ".claude" / "history.jsonl"


# ---------------------------------------------------------------------------
# load_projects
# ---------------------------------------------------------------------------


class TestLoadProjects:
    def test_missing_file(self, tmp_path: Path) -> None:
        paths = get_claude_paths(home=tmp_path)
        with pytest.raises(ClickExit):
            load_projects(paths)

    def test_malformed_json(self, tmp_path: Path) -> None:
        paths = get_claude_paths(home=tmp_path)
        paths.claude_json.write_text("not json", encoding="utf-8")
        with pytest.raises(ClickExit):
            load_projects(paths)

    def test_valid_projects(self, fake_home: ClaudeDataPaths) -> None:
        projects = load_projects(fake_home)
        assert "/home/testuser/project-alpha" in projects
        assert "/home/testuser/project-beta" in projects

    def test_empty_projects(self, tmp_path: Path) -> None:
        paths = get_claude_paths(home=tmp_path)
        paths.claude_json.write_text(json.dumps({"projects": {}}), encoding="utf-8")
        projects = load_projects(paths)
        assert projects == {}

    def test_no_projects_key(self, tmp_path: Path) -> None:
        paths = get_claude_paths(home=tmp_path)
        paths.claude_json.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        projects = load_projects(paths)
        assert projects == {}


# ---------------------------------------------------------------------------
# resolve_projects
# ---------------------------------------------------------------------------


class TestResolveProjects:
    def test_all_flag(self, fake_home: ClaudeDataPaths) -> None:
        result = resolve_projects(None, True, fake_home)
        assert len(result) == 3  # PROJECT_A, PROJECT_B, home-dir project
        assert "/home/testuser/project-alpha" in result
        assert "/home/testuser/project-beta" in result

    def test_project_flag_valid(self, fake_home: ClaudeDataPaths) -> None:
        result = resolve_projects("/home/testuser/project-alpha", False, fake_home)
        assert result == ["/home/testuser/project-alpha"]

    def test_project_flag_invalid(self, fake_home: ClaudeDataPaths) -> None:
        with pytest.raises(ClickExit):
            resolve_projects("/nonexistent/path", False, fake_home)

    def test_interactive_selection(self, fake_home: ClaudeDataPaths) -> None:
        """Test interactive mode by mocking typer.prompt."""
        with patch("claude_clean.utils.typer.prompt", return_value="1"):
            result = resolve_projects(None, False, fake_home)
        assert len(result) == 1

    def test_interactive_all(self, fake_home: ClaudeDataPaths) -> None:
        """Selecting the ALL option returns all projects."""
        with patch("claude_clean.utils.typer.prompt", return_value="4"):
            result = resolve_projects(None, False, fake_home)
        assert len(result) == 3  # PROJECT_A, PROJECT_B, home-dir project


# ---------------------------------------------------------------------------
# select_projects_interactive
# ---------------------------------------------------------------------------


class TestSelectProjectsInteractive:
    def test_single_selection(self) -> None:
        projects = ["/home/user/proj1", "/home/user/proj2"]
        with patch("claude_clean.utils.typer.prompt", return_value="1"):
            result = select_projects_interactive(projects)
        assert result == ["/home/user/proj1"]

    def test_all_selection(self) -> None:
        projects = ["/home/user/proj1", "/home/user/proj2"]
        with patch("claude_clean.utils.typer.prompt", return_value="3"):
            result = select_projects_interactive(projects)
        assert result == projects

    def test_empty_list_exits(self) -> None:
        with pytest.raises(ClickExit):
            select_projects_interactive([])


# ---------------------------------------------------------------------------
# select_scope_interactive
# ---------------------------------------------------------------------------


class TestSelectScopeInteractive:
    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [("1", "project"), ("2", "user"), ("3", "all")],
    )
    def test_valid_choices(self, input_val: str, expected: str) -> None:
        with patch("claude_clean.utils.typer.prompt", return_value=input_val):
            assert select_scope_interactive() == expected
