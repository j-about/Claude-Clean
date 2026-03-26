# Claude Clean

**Selectively purge [Claude Code](https://github.com/anthropics/claude-code) project data from your local machine.**

Claude Code stores conversation history, session artifacts, project settings, and memory files locally under `~/.claude/` and `~/.claude.json`. Over time, this data accumulates across every project you open. **claude-clean** gives you precise, surgical control over what to keep and what to remove — per project, per data category, or everything at once.

> [!CAUTION]
> All deletions performed by this tool are **permanent and irreversible**. There is no undo, no trash, and no recovery mechanism. Always run with `--dry-run` first to review the exact list of files and directories that will be affected before committing to a destructive operation.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Project Selection](#project-selection)
  - [Commands](#commands)
  - [Global Options](#global-options)
- [What Gets Deleted](#what-gets-deleted)
- [Supported Platforms](#supported-platforms)
- [Development](#development)
- [License](#license)

---

## Quick Start

The fastest way to run Claude Clean without installing it globally:

```bash
uvx claude-clean purge --dry-run
```

This launches an interactive project selector, shows you everything that would be deleted, and exits without touching the filesystem.

---

## Installation

Requires **Python 3.14** or later.

### Recommended: Run without installing (via `uvx`)

[`uvx`](https://docs.astral.sh/uv/concepts/tools/) (part of [uv](https://docs.astral.sh/uv/)) runs Python CLI tools in isolated, ephemeral environments — no global install needed:

```bash
# Run any command directly
uvx claude-clean history --all --dry-run

# Equivalent to installing + running, but leaves no footprint
uvx claude-clean purge --project /path/to/project --yes
```

This is the recommended approach for one-off or occasional use.

### Traditional: Install from PyPI

```bash
pip install claude-clean
```

After installation, the `claude-clean` command is available globally:

```bash
claude-clean --help
```

### From source

```bash
git clone https://github.com/j-about/Claude-Clean.git
cd Claude-Clean
pip install .
```

---

## Usage

### Project Selection

Every command needs to know which project(s) to operate on. Claude Clean discovers projects by reading the `"projects"` key from `~/.claude.json` — the same state file Claude Code uses internally.

There are three ways to select projects:

| Method | Flag | Behavior |
|:---|:---|:---|
| **Interactive** | *(default)* | Displays a numbered list of all known projects with an "ALL" option. You pick one or all. |
| **Explicit** | `--project PATH` / `-p PATH` | Targets a single project by its absolute path. The path must match a key in `~/.claude.json`. |
| **Blanket** | `--all` / `-a` | Targets every known project without prompting. |

**Interactive mode example:**

```
$ claude-clean history

  Known Projects
  ┌───┬─────────────────────────────────────┐
  │ # │ Project Path                        │
  ├───┼─────────────────────────────────────┤
  │ 1 │ /home/user/project-alpha            │
  │ 2 │ /home/user/project-beta             │
  │ 3 │ ALL                                 │
  └───┴─────────────────────────────────────┘

  Select a project (1-3):
```

### Commands

#### `claude-clean history`

Delete conversation history and all associated session artifacts for selected project(s).

**What it removes:**
- Matching entries from `~/.claude/history.jsonl`
- Cached paste content referenced by removed entries (`~/.claude/paste-cache/*.txt`)
- Session file-history backups (`~/.claude/file-history/{session-id}/`)
- Session environment snapshots (`~/.claude/session-env/{session-id}/`)
- Plan documents referenced in session files (`~/.claude/plans/*.md`)
- The encoded project directory (`~/.claude/projects/{encoded-path}/`)

```bash
# Interactive project selection, preview only
claude-clean history --dry-run

# Delete history for a specific project
claude-clean history --project /home/user/my-project --yes

# Delete history for all projects, skip confirmation
claude-clean history --all --yes
```

---

#### `claude-clean settings`

Delete project settings at the project scope, user scope, or both.

**Scopes:**

| Scope | What it removes |
|:---|:---|
| `project` | The `{project-root}/.claude/` directory (project-local settings, rules, commands, skills, agents, MCP config) |
| `user` | The project's entry from the `"projects"` object in `~/.claude.json` (user-level state: allowed tools, MCP servers, session metrics) |
| `all` | Both of the above |

When `--scope` is omitted, an interactive prompt asks you to choose.

```bash
# Interactive project + scope selection
claude-clean settings

# Delete project-local settings only
claude-clean settings --project /home/user/my-project --scope project --yes

# Remove user-level state for all projects
claude-clean settings --all --scope user --yes

# Full settings cleanup, preview first
claude-clean settings --all --scope all --dry-run
```

---

#### `claude-clean metadata`

Delete project memory files (`CLAUDE.md`).

**What it removes:**
- `{project-root}/CLAUDE.md`
- `{project-root}/.claude/CLAUDE.md`

```bash
# Delete memory files for a specific project
claude-clean metadata --project /home/user/my-project --yes

# Preview metadata cleanup for all projects
claude-clean metadata --all --dry-run
```

---

#### `claude-clean purge`

Run all of the above in sequence — **history**, then **settings** (scope: `all`), then **metadata** — as a single operation. This is the nuclear option for completely removing every trace of a project from Claude Code's local data.

```bash
# Full purge for a single project
claude-clean purge --project /home/user/my-project --yes

# Preview a full purge of all projects
claude-clean purge --all --dry-run

# Full purge of everything, no prompts
claude-clean purge --all --yes
```

### Global Options

These options are available on every command:

| Option | Short | Description |
|:---|:---|:---|
| `--project PATH` | `-p` | Target a specific project by its absolute path |
| `--all` | `-a` | Target all known projects |
| `--yes` | `-y` | Skip the confirmation prompt |
| `--dry-run` | | Preview the list of actions without performing any deletions |
| `--help` | | Show help for the command |

**Recommended workflow:**

```bash
# Step 1: Always preview first
claude-clean purge --project /path/to/project --dry-run

# Step 2: Review the output, then execute
claude-clean purge --project /path/to/project --yes
```

---

## What Gets Deleted

The following table maps each command to the Claude Code data it targets:

| Data | Location | `history` | `settings --scope project` | `settings --scope user` | `metadata` | `purge` |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| History entries | `~/.claude/history.jsonl` | X | | | | X |
| Paste cache | `~/.claude/paste-cache/{hash}.txt` | X | | | | X |
| Session transcripts | `~/.claude/projects/{encoded}/` | X | | | | X |
| File-history backups | `~/.claude/file-history/{session}/` | X | | | | X |
| Session environment | `~/.claude/session-env/{session}/` | X | | | | X |
| Plan documents | `~/.claude/plans/{name}.md` | X | | | | X |
| Project-local settings | `{project}/.claude/` | | X | | | X |
| User-level project state | `~/.claude.json` (projects key) | | | X | | X |
| Root memory file | `{project}/CLAUDE.md` | | | | X | X |
| Nested memory file | `{project}/.claude/CLAUDE.md` | | | | X | X |

---

## Supported Platforms

| Platform | Home directory | Status |
|:---|:---|:---:|
| **macOS** 13.0 Ventura+ | `/Users/{username}` | Supported |
| **Linux** Ubuntu 20.04+, Debian 10+, Fedora, etc. | `/home/{username}` | Supported |
| **Windows** 10 (build 1809+) / 11 (native) | `C:\Users\{username}` | Supported |
| **Windows** WSL2 | `/home/{username}` (inside WSL filesystem) | Supported |

claude-clean uses `pathlib.Path` throughout and resolves the home directory via `Path.home()`. No platform-specific APIs or hardcoded paths are used.

---

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Python 3.14+

### Setup

```bash
git clone https://github.com/j-about/Claude-Clean.git
cd Claude-Clean
uv sync --group dev
```

### Running Tests

```bash
uv run pytest tests/ -v
```

### Type Checking

```bash
uv run mypy --strict src/
```

### Linting and Formatting

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Project Structure

```
src/claude_clean/
    __init__.py       Entry point — re-exports main()
    cli.py            Typer application, commands, action execution engine
    services.py       Pure functions returning planned actions (no side effects)
    utils.py          Path encoding, project discovery, interactive selection
    models.py         Data models — Action, ActionKind, ClaudeDataPaths
tests/
    conftest.py       Shared fixtures (realistic ~/.claude/ tree under tmp_path)
    test_utils.py     Path encoding, project discovery, interactive selection
    test_services.py  Action planning for all commands
    test_cli.py       CLI integration tests via CliRunner
```

### Design Principles

- **Separation of I/O and logic.** Service functions accept paths and return lists of `Action` objects describing filesystem mutations. The CLI layer handles display, confirmation, and execution. This makes the core logic trivially testable with no mocks.

- **Atomic writes.** All JSON and JSONL rewrites use `tempfile.mkstemp()` in the same directory followed by `os.replace()`, ensuring no data corruption on crash or interrupt.

- **Batch efficiency.** When operating on multiple projects, shared files like `history.jsonl` and `~/.claude.json` are rewritten exactly once — not once per project.

---

## License

[MIT](LICENSE) — Copyright (c) 2026 Jonathan About
