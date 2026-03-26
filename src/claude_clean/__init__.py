"""claude-clean: CLI for purging Claude Code project data."""

from claude_clean.cli import app


def main() -> None:
    """Entry point for the ``claude-clean`` console script."""
    app()
