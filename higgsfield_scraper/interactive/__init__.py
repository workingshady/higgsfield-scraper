"""Interactive (menu) mode: `python -m higgsfield_scraper` with no args on a terminal, or `menu` / `-i`.

Every menu choice maps to a flag: the Scrape wizard builds the same argv the flag CLI takes, shows it, and runs it
through the same argparse parser and `cmd_*` functions (see docs/INTERACTIVE_FLOW_PLAN.md).
This module must not import questionary at import time: the flag CLI imports it to decide whether to open the menu.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

EXIT_USAGE = 2
FLAGS_HINT = "use the flag CLI instead: python -m higgsfield_scraper --help"


def _isatty(stream) -> bool:
    try:
        return bool(stream and stream.isatty())
    except (AttributeError, ValueError):
        return False


def should_auto_launch() -> bool:
    """`python -m higgsfield_scraper` with no args opens the menu only on a real terminal and outside CI."""
    if os.environ.get("CI") or os.environ.get("HF_NO_MENU"):
        return False
    return _isatty(sys.stdin) and _isatty(sys.stdout)


def prompt_problem() -> Optional[str]:
    """None if questionary can drive this terminal, else a one-line reason (with how to use flags instead)."""
    try:
        import questionary  # noqa: F401
        import rich  # noqa: F401
    except ImportError as e:
        return (f"interactive mode needs the `interactive` extra ({e.name} is not installed): "
                f'pip install "higgsfield-scraper[interactive]" -- or {FLAGS_HINT}')
    if not (_isatty(sys.stdin) and _isatty(sys.stdout)):
        return f"interactive mode needs a terminal (stdin/stdout are not a TTY) -- {FLAGS_HINT}"
    try:
        from prompt_toolkit.output.defaults import create_output
        create_output()
    except Exception as e:                        # e.g. NoConsoleScreenBufferError under mintty / Git Bash
        return (f"this terminal can't run interactive prompts ({type(e).__name__}; on Git Bash use Windows Terminal "
                f"or `winpty python -m higgsfield_scraper`) -- {FLAGS_HINT}")
    return None


def launch(prompter=None) -> int:
    """Open the menu. Returns an exit code (2 when this terminal can't prompt)."""
    if prompter is None:
        problem = prompt_problem()
        if problem:
            print(problem, file=sys.stderr)
            return EXIT_USAGE
    from .app import App
    return App(prompter=prompter).run()
