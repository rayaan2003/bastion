"""Pattern-based detection of PII and secrets in tool-call args or LLM output text.

Regex-based, not ML-based: no spaCy/Presidio model download, no extra
runtime dependency, fast enough to run inline on every call. This catches
the common, costly leaks (emails, SSNs, credit card numbers, cloud
credentials, private keys) with a fixed false-negative rate — it is not a
substitute for a proper DLP classifier. Swap in something heavier later if
that rate becomes a problem in practice; see PLAN.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    category: str
    matched_text: str
    start: int
    end: int


_DETECTORS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone_us": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn_us": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws_secret_access_key": re.compile(
        r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"
    ),
    "generic_api_key": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def available_categories() -> list[str]:
    return sorted(_DETECTORS)


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _is_valid_match(category: str, matched_text: str) -> bool:
    if category == "credit_card":
        digits = re.sub(r"[ -]", "", matched_text)
        return len(digits) in (13, 14, 15, 16) and _luhn_valid(digits)
    return True


def scan_text(text: str, categories: list[str] | None = None) -> list[Finding]:
    names = categories if categories is not None else available_categories()
    findings: list[Finding] = []
    for name in names:
        pattern = _DETECTORS.get(name)
        if pattern is None:
            raise ValueError(f"unknown category {name!r}; known: {available_categories()}")
        for m in pattern.finditer(text):
            if _is_valid_match(name, m.group(0)):
                findings.append(
                    Finding(category=name, matched_text=m.group(0), start=m.start(), end=m.end())
                )
    return findings


def redact(
    text: str, categories: list[str] | None = None, mask: str = "[REDACTED:{category}]"
) -> str:
    findings = sorted(scan_text(text, categories), key=lambda f: f.start, reverse=True)
    for f in findings:
        text = text[: f.start] + mask.format(category=f.category) + text[f.end :]
    return text


def contains_pii(categories: list[str] | None = None) -> Callable[[dict[str, Any]], bool]:
    """A PolicyEngine condition: matches if any tool-call arg contains a
    detected PII/secret category. Use as `Rule(condition=contains_pii(...))`.
    """
    def _condition(args: dict[str, Any]) -> bool:
        blob = " ".join(str(v) for v in args.values())
        return bool(scan_text(blob, categories))
    return _condition


class SensitiveContentBlocked(Exception):
    def __init__(self, findings: list[Finding]):
        self.findings = findings
        categories = ", ".join(sorted({f.category for f in findings}))
        super().__init__(f"sensitive content detected: {categories}")


def enforce_text_policy(
    text: str, *, categories: list[str] | None = None, on_detect: str = "block"
) -> str:
    """Apply scanning directly to arbitrary text — e.g. an LLM response —
    outside the tool-call path. `on_detect="block"` raises
    SensitiveContentBlocked; `on_detect="redact"` returns the text with
    matches replaced.
    """
    findings = scan_text(text, categories)
    if not findings:
        return text
    if on_detect == "block":
        raise SensitiveContentBlocked(findings)
    if on_detect == "redact":
        return redact(text, categories)
    raise ValueError(f"unknown on_detect mode {on_detect!r}; expected 'block' or 'redact'")
