# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Markdown + JSON report generation."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from guardian.core.findings import FindingStore, SEVERITY_ORDER
from guardian.core.validation import ValidationResult


def _human(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class ReportGenerator:
    """Writes analysis_*.md and analysis_*.json under reports/."""

    def __init__(self, project_root: str, config) -> None:
        self.root = project_root
        self.reports_dir = os.path.join(
            project_root, config.get("reports.directory", "reports"))

    def generate(self, engine, validation_results=None) -> tuple:
        """Return (markdown_path, json_path)."""
        os.makedirs(self.reports_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        md_path = os.path.join(self.reports_dir, f"analysis_{stamp}.md")
        json_path = os.path.join(self.reports_dir, f"analysis_{stamp}.json")

        profile = engine.profile
        store = engine.store
        findings = sorted(store.findings, key=lambda f: f.sort_key())

        sev_counts = {s: 0 for s in SEVERITY_ORDER}
        fixed_count = failed_count = 0
        for f in findings:
            sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1
            if f.status == "fixed":
                fixed_count += 1
            elif f.status == "fix_failed":
                failed_count += 1

        lines = [
            "# AI Guardian Analysis Report",
            "",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Project",
            "",
        ]
        if profile:
            lines += [f"- {l}" for l in profile.summary_lines()]
        lines += [
            f"- Mode: {engine.config.mode}",
            f"- Auto Fix: {'ENABLED' if engine.config.auto_fix else 'DISABLED'}",
            f"- Scan duration: {engine.elapsed_seconds:.0f}s",
            f"- Files analyzed: {engine.files_analyzed_count}",
            f"- Files skipped: {engine.files_skipped_count}",
            f"- API requests used: {getattr(engine.llm, 'requests_used', 0)}",
            f"- Tokens used: {getattr(engine.llm, 'tokens_used', 0)}",
            "",
            "## Findings Summary",
            "",
        ]
        for sev, count in sev_counts.items():
            if count:
                lines.append(f"- {sev}: {count}")
        lines += ["- Fixed:", str(fixed_count), "- Failed fixes:", str(failed_count), ""]

        if engine.analyzer_report:
            lines += ["## Technical Overview", "", engine.analyzer_report, ""]

        lines += ["## Detailed Findings", ""]
        if not findings:
            lines.append("No issues were reported.")
        for i, f in enumerate(findings, 1):
            status_label = f.status.upper()
            lines += [
                f"### {i}. [{f.severity}] {f.file}:{f.line} - {f.category} ({status_label})",
                f"- Description: {f.description}",
                f"- Confidence: {int(f.confidence * 100)}%",
            ]
            if f.reason:
                lines.append(f"- Why it is a problem: {f.reason}")
            if f.trigger_path:
                lines.append(f"- Trigger path: {f.trigger_path}")
            if f.expected_behavior:
                lines.append(f"- Expected behavior: {f.expected_behavior}")
            if f.suggested_fix:
                lines.append(f"- Suggested fix: {f.suggested_fix}")
            if f.recheck_result:
                lines.append(f"- Re-check result: {f.recheck_result}")
            lines.append("")

        if validation_results:
            lines += ["## Validation Results", ""]
            for vr in validation_results:
                status = "PASS" if vr.ok else "FAIL"
                lines += [f"### `{vr.command}` - {status}", "```", vr.output, "```", ""]

        if engine.errors:
            lines += ["## Errors Encountered", ""]
            lines += [f"- {e}" for e in engine.errors]
            lines.append("")

        lines += [
            "## Recommended Next Steps",
            "",
            "1. Review CRITICAL and HIGH findings that remain open.",
            "2. Run the project's full test suite manually.",
            "3. Re-run AI Guardian after applying manual changes.",
            "4. Consider adding tests around every fixed area.",
            "",
        ]

        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        machine = {
            "generated_at": datetime.now().isoformat(),
            "project": {"path": engine.root,
                        "technologies": profile.technologies if profile else [],
                        "languages": profile.languages if profile else {},
                        "files_analyzed": engine.files_analyzed_count,
                        "files_skipped": engine.files_skipped_count,
                        "size_bytes": profile.total_size_bytes if profile else 0},
            "mode": engine.config.mode,
            "auto_fix": engine.config.auto_fix,
            "duration_seconds": round(engine.elapsed_seconds, 1),
            "tokens_used": getattr(engine.llm, "tokens_used", 0),
            "requests_used": getattr(engine.llm, "requests_used", 0),
            "severity_counts": sev_counts,
            "findings": [f.to_dict() for f in findings],
            "validation": [{"command": vr.command, "ok": vr.ok, "output": vr.output}
                           for vr in (validation_results or [])],
            "errors": engine.errors,
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(machine, fh, indent=2)

        return md_path, json_path
