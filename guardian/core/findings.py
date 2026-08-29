# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Finding data model and helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
VALID_SEVERITIES = set(SEVERITY_ORDER)


@dataclass
class Finding:
    """A single issue discovered by the analysis engine."""

    file: str
    line: int = 0
    severity: str = "INFO"
    category: str = "General"
    description: str = ""
    reason: str = ""
    trigger_path: str = ""          # how the issue can be triggered
    expected_behavior: str = ""
    confidence: float = 0.5
    status: str = "open"            # open | fixed | fix_failed | wont_fix | verified_issue | inferred_issue
    suggested_fix: str = ""
    fix_applied: bool = False
    recheck_result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        known = {k for k in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER.get(self.severity, 9), -self.confidence, self.file)


def parse_findings_json(text: str) -> List[Finding]:
    """Extract a JSON array of findings from an AI reply."""
    candidates: List[str] = []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    for candidate in candidates:
        start = candidate.find("[")
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if esc:
                esc = False; continue
            if ch == "\\":
                esc = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if in_str:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    snippet = candidate[start:i + 1]
                    try:
                        raw_list = json.loads(snippet)
                        return _coerce(raw_list)
                    except ValueError:
                        break
    return []


def _coerce(raw_list: List[Any]) -> List[Finding]:
    findings: List[Finding] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "INFO")).upper()
        if sev not in VALID_SEVERITIES:
            sev = "INFO"
        try:
            conf = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.5
        try:
            line = int(item.get("line", 0) or 0)
        except (TypeError, ValueError):
            line = 0
        findings.append(Finding(
            file=str(item.get("file", "?")),
            line=line,
            severity=sev,
            category=str(item.get("category", "General")),
            description=str(item.get("description", "")),
            reason=str(item.get("reason", item.get("why", ""))),
            trigger_path=str(item.get("trigger", item.get("how_it_happens", ""))),
            expected_behavior=str(item.get("expected", item.get("expected_behavior", ""))),
            confidence=conf,
            status="open",
            suggested_fix=str(item.get("suggested_fix", item.get("fix", ""))),
        ))
    return findings


def deduplicate(findings: List[Finding]) -> List[Finding]:
    """Remove duplicate findings by (file, line-ish, normalized description)."""
    seen: set = set()
    unique: List[Finding] = []
    for f in findings:
        norm = re.sub(r"\W+", "", f.description.lower())[:80]
        key = (f.file, max(0, f.line - 5), f.line + 5, norm)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


class FindingStore:
    """In-memory store with immediate disk persistence (notepad pattern)."""

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self.findings: List[Finding] = []
        self.notepad_path = os.path.join(project_root, ".guardian_findings.md")

    def add_all(self, new_findings: List[Finding]) -> int:
        added = 0
        existing = deduplicate(self.findings + new_findings)
        added = len(existing) - len(self.findings)
        self.findings = existing
        self.flush_notepad()
        return max(added, 0)

    def update_status(self, file: str, line: int, status: str,
                      recheck: str = "", fix_applied: bool | None = None) -> None:
        for f in self.findings:
            if f.file == file and abs(f.line - line) <= 3:
                f.status = status
                if recheck:
                    f.recheck_result = recheck
                if fix_applied is not None:
                    f.fix_applied = fix_applied
        self.flush_notepad()

    def flush_notepad(self) -> None:
        """Write current findings to the live Markdown notepad immediately."""
        lines = ["# AI Guardian - Live Findings", ""]
        by_sev: Dict[str, List[Finding]] = {}
        for f in self.findings:
            by_sev.setdefault(f.severity, []).append(f)
        for sev in SEVERITY_ORDER:
            group = by_sev.get(sev, [])
            if not group:
                continue
            lines.append(f"## {sev} ({len(group)})")
            lines.append("")
            for f in sorted(group, key=lambda x: x.sort_key()):
                status_icon = {"fixed": "[FIXED]", "fix_failed": "[FAILED]",
                               "verified_issue": "[VERIFIED]", "inferred_issue": "[INFERRED]"}.get(f.status, "")
                lines.append(f"### {status_icon} {f.file}:{f.line} - {f.category}")
                lines.append(f"- Severity: {f.severity}")
                lines.append(f"- Confidence: {int(f.confidence * 100)}%")
                lines.append(f"- Status: {f.status}")
                lines.append(f"- Description: {f.description}")
                if f.reason:
                    lines.append(f"- Reason: {f.reason}")
                if f.trigger_path:
                    lines.append(f"- Trigger path: {f.trigger_path}")
                if f.expected_behavior:
                    lines.append(f"- Expected: {f.expected_behavior}")
                if f.suggested_fix:
                    lines.append(f"- Suggested fix: {f.suggested_fix}")
                if f.recheck_result:
                    lines.append(f"- Re-check: {f.recheck_result}")
                lines.append("")
        tmp_path = self.notepad_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        os.replace(tmp_path, self.notepad_path)


# Local import placed at bottom to avoid a circular module-level dependency.
import os  # noqa: E402
