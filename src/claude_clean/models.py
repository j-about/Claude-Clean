"""Data models for claude-clean."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any


class ActionKind(Enum):
    """Types of filesystem mutations the CLI can perform."""

    DELETE_FILE = auto()
    DELETE_DIR = auto()
    REWRITE_JSON = auto()
    REWRITE_JSONL = auto()


@dataclass(frozen=True, slots=True)
class Action:
    """A planned filesystem mutation."""

    kind: ActionKind
    path: Path
    description: str
    payload: Any = None  # dict for REWRITE_JSON, list[dict] for REWRITE_JSONL


@dataclass(frozen=True, slots=True)
class ClaudeDataPaths:
    """Resolved paths to all Claude Code data locations."""

    home: Path
    claude_json: Path
    claude_dir: Path
    history_jsonl: Path
    projects_dir: Path
    file_history_dir: Path
    session_env_dir: Path
    plans_dir: Path
    paste_cache_dir: Path
