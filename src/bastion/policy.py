"""Policy engine: decides ALLOW / BLOCK / APPROVE for a tool call before it executes."""

from __future__ import annotations

import fnmatch
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_log = logging.getLogger("bastion")


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
    shadow: if True, the rule is evaluated and its outcome audited as
        `would_<action>`, but never enforced — for trialling a rule against
        real traffic before turning it on.
    """

    tool_pattern: str
    action: Action
    condition: Callable[[dict[str, Any]], bool] | None = None
    reason: str = ""
    name: str = ""
    shadow: bool = False

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
    reason: str
    # What would have happened had shadow rules been enforced. Only set when
    # that differs from `action`.
    shadow: Decision | None = None


def _rule_decision(rule: Rule, tool_name: str, args: dict[str, Any]) -> Decision:
    reason = rule.reason or f"matched rule '{rule.name or rule.tool_pattern}'"
    return Decision(rule.action, rule, tool_name, args, reason)


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
    """Evaluates rules in order; first match wins. No match => `default_action`.

    shadow: if True, nothing is enforced — every rule and the default action
    behave as shadow rules (see `Rule.shadow`), so every call is allowed and
    the policy's would-be decisions are audited. For rolling bastion out
    against real traffic before it can block anything.
    """

    rules: list[Rule] = field(default_factory=list)
    default_action: Action = Action.ALLOW
    shadow: bool = False

    def add_rule(self, rule: Rule) -> PolicyEngine:
        self.rules.append(rule)
        return self

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> Decision:
        # Shadow rules are skipped over, not stopped at, so adding one can
        # never change the enforced outcome of the rules behind it.
        enforced: Decision | None = None
        would: Decision | None = None
        for rule in self.rules:
            is_shadow = rule.shadow or self.shadow
            if is_shadow and would is not None:
                continue
            if not self._matches(rule, is_shadow, tool_name, args):
                continue
            decision = _rule_decision(rule, tool_name, args)
            if would is None:
                would = decision
            if not is_shadow:
                enforced = decision
                break

        default = Decision(
            self.default_action,
            None,
            tool_name,
            args,
            f"no matching rule — default {self.default_action.value}",
        )
        if would is None:
            would = default
        if enforced is None:
            enforced = (
                Decision(Action.ALLOW, None, tool_name, args, "shadow mode — policy not enforced")
                if self.shadow
                else default
            )
        if would.action != enforced.action:
            enforced.shadow = would
        return enforced

    @staticmethod
    def _matches(rule: Rule, is_shadow: bool, tool_name: str, args: dict[str, Any]) -> bool:
        if not is_shadow:
            return rule.matches(tool_name, args)
        # A shadow rule is on trial; a bug in it mustn't break the tool call.
        try:
            return rule.matches(tool_name, args)
        except Exception:
            _log.warning(
                "shadow rule '%s' condition raised; treating as no match",
                rule.name or rule.tool_pattern,
                exc_info=True,
            )
            return False
