"""Secret detection and redaction before content is sent to the AI API."""

from __future__ import annotations

import re
from typing import List, Tuple

# (name, compiled pattern, replacement label)
_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    ("API key", re.compile(
        r"(?i)(?:api[_-]?key|apikey|api[_-]?token)\s*[=:]\s*['\"]([A-Za-z0-9_\-\.]{16,})['\"]"),
     r"\1=<REDACTED_API_KEY>"),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{20,}"), "Bearer <REDACTED_TOKEN>"),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<REDACTED_AWS_KEY>"),
    ("Private key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"),
     "<REDACTED_PRIVATE_KEY>"),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
     "<REDACTED_JWT>"),
    ("Password literal", re.compile(
        r"(?i)\b(pass(word)?|pwd|secret)\s*[=:]\s*['\"][^'\"]{6,}['\"]"),
     "<REDACTED_PASSWORD>"),
    ("Database URL", re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s'\"<>]{8,}"),
     "<REDACTED_DATABASE_URL>"),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "<REDACTED_SLACK_TOKEN>"),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "<REDACTED_GITHUB_TOKEN>"),
    ("Generic hex secret", re.compile(
        r"(?i)\b(secret|token|credential)s?[_.](?:hash|value|hex)?\s*[=:]\s*['\"][a-f0-9]{32,}['\"]"),
     "<REDACTED_HEX_SECRET>"),
]

ENV_ASSIGNMENT = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)=(\S{6,})$")


def redact(content: str) -> Tuple[str, List[str]]:
    """Redact secrets from text. Returns (clean_text, list_of_redaction_labels)."""
    found: List[str] = []
    result = content
    for name, pattern, replacement in _PATTERNS:
        if pattern.search(result):
            result = pattern.sub(replacement, result)
            found.append(name)
    # Generic .env style assignments for secret-looking variable names
    def _env_sub(match: re.Match) -> str:
        var, value = match.group(1), match.group(2)
        if any(k in var.upper() for k in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASS")):
            return f"{var}=<REDACTED_ENV_VALUE>"
        return match.group(0)
    new_result = ENV_ASSIGNMENT.sub(_env_sub, result)
    if new_result != result:
        found.append("Environment assignment")
        result = new_result
    return result, sorted(set(found))


def contains_secret(content: str) -> bool:
    """Quick boolean check without transforming."""
    _, labels = redact(content)
    return bool(labels)


class SecretGuard:
    """Tracks redaction stats for the session report."""

    def __init__(self) -> None:
        self.redactions_total = 0
        self.files_affected: set = set()

    def guard(self, relative_path: str, content: str) -> str:
        clean, labels = redact(content)
        if labels:
            self.redactions_total += len(labels)
            self.files_affected.add(relative_path)
        return clean
