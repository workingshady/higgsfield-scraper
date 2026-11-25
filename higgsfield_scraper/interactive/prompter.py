"""Prompt backend. Screens talk to a Prompter, never to questionary directly, so tests can inject answers.

Every method returns None when the user cancels (Ctrl-C / Ctrl-D) — screens treat that as "back".
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional, Sequence

Choices = Sequence[tuple[str, Any]]           # (title, value)


class Prompter:
    def select(self, message: str, choices: Choices, default: Any = None, instruction: Optional[str] = None) -> Any:
        raise NotImplementedError

    def checkbox(self, message: str, choices: Choices, checked: Sequence[Any] = (), min_one: bool = False,
                 instruction: Optional[str] = None) -> Optional[list]:
        raise NotImplementedError

    def confirm(self, message: str, default: bool = False) -> Optional[bool]:
        raise NotImplementedError

    def text(self, message: str, default: str = "", validate: Optional[Callable[[str], Any]] = None,
             instruction: Optional[str] = None) -> Optional[str]:
        raise NotImplementedError

    def password(self, message: str, validate: Optional[Callable[[str], Any]] = None) -> Optional[str]:
        raise NotImplementedError


class QuestionaryPrompter(Prompter):
    def __init__(self, **io: Any) -> None:
        """`io`: optional prompt_toolkit `input=` / `output=` (tests drive it with a pipe input)."""
        import questionary
        self.io = io
        from questionary import Style
        self.q = questionary
        self.style = None if os.environ.get("NO_COLOR") else Style([
            ("qmark", "fg:#00afff bold"), ("pointer", "fg:#00afff bold"), ("highlighted", "fg:#00afff bold"),
            ("selected", "fg:#5fd75f"), ("answer", "fg:#5fd75f bold"), ("instruction", "fg:#808080")])

    def _ask(self, question) -> Any:
        return question.ask(kbi_msg="")          # Ctrl-C -> None (no "Cancelled by user" noise)

    def select(self, message, choices, default=None, instruction=None):
        cs = [self.q.Choice(t, v) for t, v in choices]
        dflt = next((c for c in cs if c.value == default), None)
        return self._ask(self.q.select(message, cs, default=dflt, style=self.style, instruction=instruction,
                                       use_shortcuts=False, **self.io))

    def checkbox(self, message, choices, checked=(), min_one=False, instruction=None):
        cs = [self.q.Choice(t, v, checked=v in checked) for t, v in choices]
        val = (lambda xs: bool(xs) or "pick at least one (space toggles)") if min_one else (lambda xs: True)
        return self._ask(self.q.checkbox(message, cs, validate=val, style=self.style,
                                         instruction=instruction or "(space toggles, a = all, enter = ok)", **self.io))

    def confirm(self, message, default=False):
        return self._ask(self.q.confirm(message, default=default, style=self.style, **self.io))

    def text(self, message, default="", validate=None, instruction=None):
        return self._ask(self.q.text(message, default=default or "", validate=validate or (lambda s: True),
                                     style=self.style, instruction=instruction, **self.io))

    def password(self, message, validate=None):
        return self._ask(self.q.password(message, validate=validate or (lambda s: True), style=self.style,
                                         **self.io))


class ScriptedPrompter(Prompter):
    """Answers from a list, in order (tests / scripted demos). Validators are applied: an invalid scripted answer
    raises AssertionError. A callable answer receives (method, message, kwargs) and returns the answer."""

    def __init__(self, answers: Sequence[Any]):
        self.answers = list(answers)
        self.asked: list[tuple[str, str]] = []

    def _next(self, method: str, message: str, **kw) -> Any:
        self.asked.append((method, message))
        if not self.answers:
            raise AssertionError(f"no scripted answer left for {method}: {message!r}")
        ans = self.answers.pop(0)
        if callable(ans):
            ans = ans(method, message, kw)
        return ans

    def select(self, message, choices, default=None, instruction=None):
        ans = self._next("select", message, choices=choices, default=default)
        if ans is not None and ans not in [v for _, v in choices]:
            raise AssertionError(f"{ans!r} is not a choice of {message!r}: {[v for _, v in choices]}")
        return ans

    def checkbox(self, message, choices, checked=(), min_one=False, instruction=None):
        ans = self._next("checkbox", message, choices=choices, checked=checked)
        if ans is not None:
            bad = [a for a in ans if a not in [v for _, v in choices]]
            assert not bad, f"{bad} not in choices of {message!r}"
            assert not (min_one and not ans), f"{message!r} needs at least one"
        return ans

    def confirm(self, message, default=False):
        return self._next("confirm", message, default=default)

    def text(self, message, default="", validate=None, instruction=None):
        ans = self._next("text", message, default=default)
        if ans is ...:                                # Ellipsis = accept the default
            ans = default
        if ans is not None and validate is not None:
            ok = validate(ans)
            assert ok is True, f"{message!r}: {ans!r} rejected: {ok}"
        return ans

    def password(self, message, validate=None):
        ans = self._next("password", message)
        if ans is not None and validate is not None:
            ok = validate(ans)
            assert ok is True, f"{message!r}: rejected: {ok}"
        return ans
