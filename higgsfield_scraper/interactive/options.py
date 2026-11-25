"""argparse -> questions -> argv. Fully dynamic: reads the actions of the `scrape <name>` subparser that
`cli.build_parser()` builds, so a scraper added to the registry shows up in the menu with all of its options.

Mapping: choices -> select (checkbox when the flag can repeat) · store_true/store_false -> confirm ·
int/float -> validated text · count (-v) -> integer · everything else -> text. Answers that equal the argparse
default produce no flag, so the equivalent command line stays short.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Asked elsewhere in the wizard (label, dry run) or never asked (secrets / internals).
SKIP_DESTS = {"help", "token", "dry_run", "label", "scraper", "func", "command"}
# Shared groups (core/cli_common.py) — shown after the scraper's own groups, in this order.
COMMON_GROUPS = ("limits", "media download (optional)", "access / safety", "run", "logging")
DEFAULT_GROUPS = ("limits",)          # also pre-ticked in "customize" next to the scraper's own groups
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")   # folder suffix (slugified by RunContext)


@dataclass
class Question:
    dest: str
    kind: str                          # select | checkbox | confirm | int | float | count | text
    flag: str                          # option string used in the command line
    help: str
    default: Any
    group: str
    choices: Optional[list] = None
    actions: list = field(default_factory=list)
    type: Optional[Callable] = None
    append: bool = False

    @property
    def title(self) -> str:
        """Prompt text. Confirms are phrased by destination (`write markdown?` for --no-markdown), so
        yes/no always means "this setting on/off" whichever flag spells it."""
        return self.dest.replace("_", " ") if self.kind == "confirm" else self.flag.lstrip("-")

    def initial(self, prev: Any = None) -> Any:
        """Value to pre-fill: the remembered answer, else the argparse default (prompt-friendly form)."""
        v = self.default if prev is None else prev
        if self.kind == "confirm":
            return bool(v)
        if self.kind == "checkbox":
            return list(v or [])
        if self.kind == "select":
            return v if v in (self.choices or []) else (self.choices or [None])[0]
        return "" if v is None else (",".join(map(str, v)) if isinstance(v, list) else str(v))

    def validate(self, text: str) -> bool | str:
        """questionary validator for text-like kinds."""
        s = (text or "").strip()
        if s == "":
            return True                            # empty = keep the default
        if self.kind in ("int", "count"):
            try:
                return True if int(s) >= 0 else "must be 0 or more"
            except ValueError:
                return "enter a whole number (or leave empty for the default)"
        if self.kind == "float":
            try:
                return True if float(s) >= 0 else "must be 0 or more"
            except ValueError:
                return "enter a number (or leave empty for the default)"
        if self.type is not None and self.type is not str:
            try:
                self.type(s)
            except Exception as e:                 # argparse would reject it too
                return f"invalid value: {e}"
        return True

    def to_argv(self, value: Any) -> list[str]:
        if self.kind == "confirm":
            value = bool(value)
            if value == bool(self.default):
                return []
            act = next((a for a in self.actions if getattr(a, "const", None) is value), None)
            return [_long(act)] if act is not None else []       # inexpressible (no flag for it) -> keep default
        if self.kind == "count":
            n = int(str(value).strip() or 0) if value not in (None, "") else int(self.default or 0)
            return [self.flag] * n if n != int(self.default or 0) else []
        if self.kind == "checkbox":
            vals = list(value or [])
            if sorted(map(str, vals)) == sorted(map(str, self.default or [])):
                return []
            return [x for v in vals for x in _opt(self.flag, str(v))]
        if self.kind == "select":
            return [] if value is None or value == self.default else _opt(self.flag, str(value))
        s = "" if value is None else (",".join(map(str, value)) if isinstance(value, list) else str(value)).strip()
        if s == "" or (self.default is not None and not self.append and s == _fmt_default(self.default)):
            return []
        return _opt(self.flag, s)


def _long(action: argparse.Action) -> str:
    return next((o for o in action.option_strings if o.startswith("--")), action.option_strings[0])


def _opt(flag: str, value: str) -> list[str]:
    return [f"{flag}={value}"] if value.startswith("-") else [flag, value]


def _fmt_default(v: Any) -> str:
    return ",".join(map(str, v)) if isinstance(v, list) else str(v)


# ------------------------------------------------------------------ parser introspection
def _subparsers(p: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))


def scrape_subparser(name: str, parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    """The `scrape <name>` subparser exactly as the flag CLI builds it."""
    from ..cli import build_parser
    root = parser or build_parser()
    scrape = _subparsers(root).choices["scrape"]
    return _subparsers(scrape).choices[name]


def _kind(a: argparse.Action) -> str:
    if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)) or (
            isinstance(a, argparse._StoreConstAction) and isinstance(a.const, bool)):
        return "confirm"
    if isinstance(a, argparse._CountAction):
        return "count"
    if a.choices:
        return "checkbox" if isinstance(a, argparse._AppendAction) else "select"
    if a.type is int:
        return "int"
    if a.type is float:
        return "float"
    return "text"


def questions_for(name: str, parser: Optional[argparse.ArgumentParser] = None) -> list[Question]:
    """One Question per destination of `scrape <name>`, grouped: scraper's own groups first, then shared ones."""
    sp = scrape_subparser(name, parser)
    by_dest: dict[str, Question] = {}
    ordered: list[tuple[int, int, Question]] = []
    for gi, group in enumerate(sp._action_groups):
        title = group.title or "options"
        rank = COMMON_GROUPS.index(title) + 1 if title in COMMON_GROUPS else 0
        for a in group._group_actions:
            if a.dest in SKIP_DESTS or not a.option_strings or a.help == argparse.SUPPRESS:
                continue
            if a.dest in by_dest:                      # e.g. --with-content / --no-content share one dest
                q = by_dest[a.dest]
                q.actions.append(a)
                q.help = f"{q.help} | {_long(a)}: {_help(a, sp)}" if a.help else q.help
                continue
            kind = _kind(a)
            q = Question(dest=a.dest, kind=kind, flag=_long(a), help=_help(a, sp), default=sp.get_default(a.dest),
                         group=title, choices=list(a.choices) if a.choices else None, actions=[a], type=a.type,
                         append=isinstance(a, argparse._AppendAction))
            by_dest[a.dest] = q
            ordered.append((rank, gi, q))
    return [q for _, _, q in sorted(ordered, key=lambda t: (t[0], t[1]))]


def _help(a: argparse.Action, sp: argparse.ArgumentParser) -> str:
    text = a.help or ""
    if "%(" in text:
        try:
            text = text % {**vars(a), "default": sp.get_default(a.dest), "prog": sp.prog}
        except (KeyError, TypeError, ValueError):
            pass
    return " ".join(text.split())


def groups_of(questions: list[Question]) -> list[str]:
    return list(dict.fromkeys(q.group for q in questions))


# ------------------------------------------------------------------ answers -> argv
def build_argv(name: str, answers: dict[str, Any], label: Optional[str] = None,
               questions: Optional[list[Question]] = None) -> list[str]:
    """`scrape <name>` + one flag per answer that differs from its default (+ --label)."""
    argv = ["scrape", name]
    for q in questions if questions is not None else questions_for(name):
        if q.dest in answers:
            argv += q.to_argv(answers[q.dest])
    if label:
        argv += ["--label", label]
    return argv


def parse_argv(argv: list[str]) -> tuple[Optional[argparse.Namespace], Optional[str]]:
    """Parse with the flag CLI's own parser. (namespace, None) or (None, argparse's error message)."""
    from ..cli import build_parser
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return build_parser().parse_args(argv), None
    except SystemExit:
        lines = [x for x in err.getvalue().strip().splitlines() if x.strip()]
        return None, (lines[-1] if lines else "invalid arguments")


def suggested_label(argv: list[str]) -> Optional[str]:
    """The label `scrape` would pick for this argv (None when the options are invalid)."""
    from ..cli import default_label
    a, _ = parse_argv(argv)
    if a is None:
        return None
    try:
        return default_label(a)
    except Exception:
        return None


def validate_label(text: str) -> bool | str:
    s = (text or "").strip()
    if s == "" or LABEL_RE.match(s):
        return True
    return "letters, digits, '.', '_' and '-' only (start with a letter or digit, max 48)"


def command_line(argv: list[str], prog: str = "python -m higgsfield_scraper") -> str:
    if os.name == "nt":
        return f"{prog} {subprocess.list2cmdline(argv)}"
    return f"{prog} {' '.join(shlex.quote(x) for x in argv)}"


def changed(name: str, answers: dict[str, Any], questions: Optional[list[Question]] = None) -> list[tuple[str, str]]:
    """(flag, value) pairs that differ from the defaults, for the summary table."""
    out = []
    for q in questions if questions is not None else questions_for(name):
        if q.dest in answers and q.to_argv(answers[q.dest]):
            v = answers[q.dest]
            out.append((q.flag, ", ".join(map(str, v)) if isinstance(v, list) else str(v)))
    return out
