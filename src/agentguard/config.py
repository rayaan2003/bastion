"""Load a PolicyEngine from a YAML file.

Lets policies be defined declaratively (policy.yaml) instead of hand-written
Python, so a non-engineer reviewer (security/compliance) can read and edit
the rules without touching code.

Schema:

    default_action: allow   # or block / approve

    rules:
      - name: block-deletes          # optional, shown in logs/approval prompts
        tool: "delete_*"             # glob pattern matched against the tool name
        action: block                # allow / block / approve
        reason: "irreversible action"
        condition:                   # optional; omit to match on `tool` alone
          type: arg_exceeds          # arg_exceeds / arg_matches_regex / any_arg_contains
          arg: amount
          threshold: 500
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from agentguard.policy import (
    Action,
    PolicyEngine,
    Rule,
    any_arg_contains,
    arg_exceeds,
    arg_matches_regex,
)

Condition = Callable[[dict[str, Any]], bool]
_ConditionBuilder = Callable[[dict[str, Any]], Condition]

_CONDITION_BUILDERS: dict[str, _ConditionBuilder] = {
    "arg_exceeds": lambda cfg: arg_exceeds(cfg["arg"], cfg["threshold"]),
    "arg_matches_regex": lambda cfg: arg_matches_regex(cfg["arg"], cfg["pattern"]),
    "any_arg_contains": lambda cfg: any_arg_contains(cfg["substrings"]),
}


class PolicyConfigError(Exception):
    """Raised when a policy YAML file is malformed."""


def load_policy_from_yaml(path: str | Path) -> PolicyEngine:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return policy_from_dict(raw)


def policy_from_dict(data: dict[str, Any]) -> PolicyEngine:
    engine = PolicyEngine(default_action=_parse_action(data.get("default_action", "allow")))
    for raw_rule in data.get("rules", []):
        engine.add_rule(_rule_from_dict(raw_rule))
    return engine


def _rule_from_dict(raw: dict[str, Any]) -> Rule:
    try:
        tool_pattern = raw["tool"]
        action = _parse_action(raw["action"])
    except KeyError as e:
        raise PolicyConfigError(f"rule missing required field: {e}") from e

    condition = _condition_from_dict(raw["condition"]) if "condition" in raw else None

    return Rule(
        tool_pattern=tool_pattern,
        action=action,
        condition=condition,
        reason=raw.get("reason", ""),
        name=raw.get("name", ""),
    )


def _condition_from_dict(raw: dict[str, Any]) -> Condition:
    try:
        condition_type = raw["type"]
    except KeyError as e:
        raise PolicyConfigError("condition missing required field: type") from e

    builder = _CONDITION_BUILDERS.get(condition_type)
    if builder is None:
        known = ", ".join(sorted(_CONDITION_BUILDERS))
        raise PolicyConfigError(
            f"unknown condition type {condition_type!r}; known types: {known}"
        )

    try:
        return builder(raw)
    except KeyError as e:
        raise PolicyConfigError(
            f"condition {condition_type!r} missing required field: {e}"
        ) from e


def _parse_action(value: str) -> Action:
    try:
        return Action(value)
    except ValueError as e:
        known = ", ".join(a.value for a in Action)
        raise PolicyConfigError(f"unknown action {value!r}; known actions: {known}") from e
