"""Policy engine: decides ALLOW / BLOCK / APPROVE for a tool call before it executes."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Action(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    APPROVE = "approve"


@dataclass
class Rule:
    """A single policy rule.

    tool_pattern: glob pattern matched against the tool name (e.g. "send_*", "delete_*", "*").
    condition: optional callable(args: dict) -> bool. If omitted, the rule matches
        on tool_pattern alone (any call to that tool).
    action: what to do when tool_pattern + condition match.
    reason: human-readable explanation, shown in logs and approval prompts.
    """

    tool_pattern: str
    action: Action
    condition: Callable[[dict[str, Any]], bool] | None = None
    reason: str = ""
    name: str = ""

    def matches(self, tool_name: str, args: dict[str, Any]) -> bool:
        if not fnmatch.fnmatch(tool_name, self.tool_pattern):
            return False
        if self.condition is not None:
            return bool(self.condition(args))
        return True


@dataclass
class Decision:
    action: Action
    rule: Rule | None
    tool_name: str
    args: dict[str, Any]

    @property
    def reason(self) -> str:
        if self.rule is None:
            return "no matching rule — default allow"
        return self.rule.reason or f"matched rule '{self.rule.name or self.rule.tool_pattern}'"


# --- Common condition helpers ---------------------------------------------------

def arg_matches_regex(arg_name: str, pattern: str) -> Callable[[dict[str, Any]], bool]:
    compiled = re.compile(pattern)
    def _cond(args: dict[str, Any]) -> bool:
        value = args.get(arg_name)
        return value is not None and bool(compiled.search(str(value)))
    return _cond


def arg_exceeds(arg_name: str, threshold: float) -> Callable[[dict[str, Any]], bool]:
    def _cond(args: dict[str, Any]) -> bool:
        value = args.get(arg_name)
        try:
            return value is not None and float(value) > threshold
        except (TypeError, ValueError):
            return False
    return _cond


def any_arg_contains(substrings: list[str]) -> Callable[[dict[str, Any]], bool]:
    lowered = [s.lower() for s in substrings]
    def _cond(args: dict[str, Any]) -> bool:
        blob = " ".join(str(v) for v in args.values()).lower()
        return any(s in blob for s in lowered)
    return _cond


# --- Engine -----------------------------------------------------------------------

@dataclass
class PolicyEngine:
    """Evaluates rules in order; first match wins. No match => ALLOW by default."""

    rules: list[Rule] = field(default_factory=list)
    default_action: Action = Action.ALLOW

    def add_rule(self, rule: Rule) -> PolicyEngine:
        self.rules.append(rule)
        return self

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> Decision:
        for rule in self.rules:
            if rule.matches(tool_name, args):
                return Decision(action=rule.action, rule=rule, tool_name=tool_name, args=args)
        return Decision(action=self.default_action, rule=None, tool_name=tool_name, args=args)
