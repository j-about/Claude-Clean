"""Pure service functions that plan filesystem actions without side effects."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from claude_clean.models import Action, ActionKind, ClaudeDataPaths
from claude_clean.utils import encode_project_path

logger = logging.getLogger(__name__)

# Pattern to extract .md filenames referenced in session files.
# Matches filenames like "elegant-dreaming-otter.md" in plan references.
_PLAN_REF_PATTERN = re.compile(r"\b([\w][\w.-]*\.md)\b")


# ---------------------------------------------------------------------------
# History cleanup
# ---------------------------------------------------------------------------


def plan_history_cleanup(
    project_paths: list[str],
    paths: ClaudeDataPaths,
) -> list[Action]:
    """Plan removal of conversation history for the given projects.

    Steps per the spec:
    1-3. Filter history.jsonl, collect paste-cache files to delete.
    4-6. Scan project session dirs for file-history, session-env, plans.

    Returns a list of :class:`Action` objects (no I/O performed).
    """
    actions: list[Action] = []
    target_set = set(project_paths)

    # --- Steps 1-3: history.jsonl filtering ---
    actions.extend(_plan_history_jsonl_filter(target_set, paths))

    # --- Steps 4-6: per-project session artifacts ---
    for project_path in project_paths:
        actions.extend(_plan_project_session_artifacts(project_path, paths))

    return actions


def _plan_history_jsonl_filter(
    target_set: set[str],
    paths: ClaudeDataPaths,
) -> list[Action]:
    """Filter history.jsonl and plan paste-cache deletions."""
    actions: list[Action] = []

    if not paths.history_jsonl.exists():
        logger.debug("history.jsonl does not exist, skipping")
        return actions

    remaining: list[dict[str, Any]] = []
    try:
        text = paths.history_jsonl.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read %s", paths.history_jsonl)
        return actions

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            # Keep malformed lines to avoid data loss
            remaining.append({"_raw": stripped})
            continue

        if entry.get("project") in target_set:
            # Collect paste-cache files to delete
            pasted: dict[str, Any] = entry.get("pastedContents", {})
            if isinstance(pasted, dict) and pasted:
                for content_hash in pasted:
                    cache_file = paths.paste_cache_dir / f"{content_hash}.txt"
                    if cache_file.exists():
                        actions.append(
                            Action(
                                kind=ActionKind.DELETE_FILE,
                                path=cache_file,
                                description=f"Delete paste cache: {cache_file.name}",
                            )
                        )
            # Line is removed (not added to remaining)
        else:
            remaining.append(entry)

    # Rewrite history.jsonl with remaining entries
    # Serialize: entries with _raw key are kept as-is
    serialized: list[dict[str, Any]] = []
    for entry in remaining:
        if "_raw" in entry:
            # Will be handled specially during write
            serialized.append(entry)
        else:
            serialized.append(entry)

    actions.append(
        Action(
            kind=ActionKind.REWRITE_JSONL,
            path=paths.history_jsonl,
            description="Rewrite history.jsonl (filtered)",
            payload=serialized,
        )
    )

    return actions


def _plan_project_session_artifacts(
    project_path: str,
    paths: ClaudeDataPaths,
) -> list[Action]:
    """Plan cleanup of session dirs, file-history, session-env, and plans."""
    actions: list[Action] = []
    encoded = encode_project_path(project_path)
    project_dir = paths.projects_dir / encoded

    if not project_dir.exists():
        logger.debug("Project dir does not exist: %s", project_dir)
        return actions

    # Scan root-level entries of the encoded project directory
    try:
        entries = list(project_dir.iterdir())
    except OSError:
        logger.warning("Could not list %s", project_dir)
        return actions

    for entry in entries:
        if entry.is_dir():
            # Directory name = session ID
            session_id = entry.name

            fh_dir = paths.file_history_dir / session_id
            if fh_dir.exists():
                actions.append(
                    Action(
                        kind=ActionKind.DELETE_DIR,
                        path=fh_dir,
                        description=f"Delete file-history: {session_id}",
                    )
                )

            se_dir = paths.session_env_dir / session_id
            if se_dir.exists():
                actions.append(
                    Action(
                        kind=ActionKind.DELETE_DIR,
                        path=se_dir,
                        description=f"Delete session-env: {session_id}",
                    )
                )
        elif entry.is_file():
            # Extract .md plan references from file content
            try:
                content = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            seen_plans: set[str] = set()
            for match in _PLAN_REF_PATTERN.finditer(content):
                plan_name = match.group(1)
                if plan_name in seen_plans:
                    continue
                seen_plans.add(plan_name)
                plan_file = paths.plans_dir / plan_name
                if plan_file.exists():
                    actions.append(
                        Action(
                            kind=ActionKind.DELETE_FILE,
                            path=plan_file,
                            description=f"Delete plan: {plan_name}",
                        )
                    )

    # Delete the entire project session directory
    actions.append(
        Action(
            kind=ActionKind.DELETE_DIR,
            path=project_dir,
            description=f"Delete project dir: {encoded}",
        )
    )

    return actions


# ---------------------------------------------------------------------------
# Settings cleanup
# ---------------------------------------------------------------------------


def plan_settings_cleanup(
    project_paths: list[str],
    paths: ClaudeDataPaths,
    scope: str,
) -> list[Action]:
    """Plan settings deletion at the given scope.

    Args:
        project_paths: Selected project absolute paths.
        paths: Resolved Claude data paths.
        scope: One of ``"project"``, ``"user"``, or ``"all"``.
    """
    actions: list[Action] = []

    if scope in ("project", "all"):
        for project_path in project_paths:
            proj_claude_dir = Path(project_path) / ".claude"
            if proj_claude_dir.exists():
                actions.append(
                    Action(
                        kind=ActionKind.DELETE_DIR,
                        path=proj_claude_dir,
                        description=f"Delete project settings: {proj_claude_dir}",
                    )
                )

    if scope in ("user", "all"):
        actions.extend(_plan_claude_json_key_removal(project_paths, paths))

    return actions


def _plan_claude_json_key_removal(
    project_paths: list[str],
    paths: ClaudeDataPaths,
) -> list[Action]:
    """Plan removal of project keys from ~/.claude.json."""
    if not paths.claude_json.exists():
        return []

    try:
        data = json.loads(paths.claude_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        logger.warning("Could not read %s for key removal", paths.claude_json)
        return []

    projects: dict[str, Any] = data.get("projects", {})
    if not isinstance(projects, dict):
        return []

    keys_to_remove = set(project_paths) & set(projects.keys())
    if not keys_to_remove:
        return []

    new_projects = {k: v for k, v in projects.items() if k not in keys_to_remove}
    data["projects"] = new_projects

    return [
        Action(
            kind=ActionKind.REWRITE_JSON,
            path=paths.claude_json,
            description=(
                f"Remove {len(keys_to_remove)} project(s) from {paths.claude_json.name}"
            ),
            payload=data,
        )
    ]


# ---------------------------------------------------------------------------
# Metadata cleanup
# ---------------------------------------------------------------------------


def plan_metadata_cleanup(
    project_paths: list[str],
    paths: ClaudeDataPaths,  # noqa: ARG001
) -> list[Action]:
    """Plan deletion of CLAUDE.md memory files for the given projects."""
    actions: list[Action] = []

    for project_path in project_paths:
        root = Path(project_path)

        root_md = root / "CLAUDE.md"
        if root_md.exists():
            actions.append(
                Action(
                    kind=ActionKind.DELETE_FILE,
                    path=root_md,
                    description=f"Delete metadata: {root_md}",
                )
            )

        nested_md = root / ".claude" / "CLAUDE.md"
        if nested_md.exists():
            actions.append(
                Action(
                    kind=ActionKind.DELETE_FILE,
                    path=nested_md,
                    description=f"Delete metadata: {nested_md}",
                )
            )

    return actions


# ---------------------------------------------------------------------------
# Full purge
# ---------------------------------------------------------------------------


def plan_purge(
    project_paths: list[str],
    paths: ClaudeDataPaths,
) -> list[Action]:
    """Plan a full purge: history + settings(all) + metadata.

    Deduplicates actions by ``(kind, path)``.
    """
    all_actions: list[Action] = []
    all_actions.extend(plan_history_cleanup(project_paths, paths))
    all_actions.extend(plan_settings_cleanup(project_paths, paths, scope="all"))
    all_actions.extend(plan_metadata_cleanup(project_paths, paths))

    # Deduplicate by (kind, path), preserving order
    seen: set[tuple[ActionKind, Path]] = set()
    deduped: list[Action] = []
    for action in all_actions:
        key = (action.kind, action.path)
        if key not in seen:
            seen.add(key)
            deduped.append(action)

    return deduped
