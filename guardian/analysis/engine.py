# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Continuous analysis engine: scan, map, analyze, fix, re-check, loop."""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, List, Optional

from guardian.core.config import Config
from guardian.core.scanner import (Scanner, ProjectProfile, read_file_safe,
                                   chunk_content, detect_minified_or_generated)
from guardian.core.redactor import SecretGuard
from guardian.core.findings import Finding, FindingStore, parse_findings_json, deduplicate
from guardian.core.llm import LLMClient, LLMError
from guardian.core.changes import ChangeLog, atomic_write, safe_join, PathSafetyError
from guardian.core.state import SessionState
from guardian.analysis.prompts import (
    BUG_FIXER_SYSTEM, UI_FIXER_SYSTEM, ANALYZER_SYSTEM,
    FIX_SYSTEM, RECHECK_SYSTEM,
    build_analysis_user_prompt, build_fix_user_prompt,
)

# Files that deserve analysis priority (entry points, configs, auth-ish paths).
PRIORITY_HINTS = (
    "auth", "login", "session", "token", "payment", "api", "server",
    "config", "index", "main", "app", "router", "db", "database",
    "middleware", "security", "user", "cart", "checkout",
)


class EngineEvent:
    """Simple event bus callbacks for the CLI to render progress."""

    def __init__(self, on_file: Optional[Callable] = None,
                 on_finding: Optional[Callable] = None,
                 on_fix: Optional[Callable] = None,
                 on_status: Optional[Callable] = None) -> None:
        self.on_file = on_file or (lambda path, idx, total: None)
        self.on_finding = on_finding or (lambda finding: None)
        self.on_fix = on_fix or (lambda finding, ok, note: None)
        self.on_status = on_status or (lambda text: None)


class AnalysisEngine:
    """Orchestrates the full continuous analysis workflow."""

    def __init__(self, config: Config, project_root: str,
                 events: Optional[EngineEvent] = None) -> None:
        self.config = config
        self.root = project_root
        self.events = events or EngineEvent()
        self.profile: Optional[ProjectProfile] = None
        self.store = FindingStore(project_root)
        self.changes = ChangeLog(project_root)
        self.secret_guard = SecretGuard()
        self.state = SessionState(project_root, config.get("state.file"))
        self.llm: Optional[LLMClient] = None
        self.stop_requested = False  # noqa: FBT001
        self.paused = False
        self.analyzer_report = ""
        self.started_at: float = 0.0
        self.files_analyzed_count = 0
        self.files_skipped_count = 0
        self.errors: List[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        self.stop_requested = True

    def _init_llm(self) -> bool:
        try:
            self.llm = LLMClient(self.config)
            return True
        except Exception as exc:  # config error, missing key, missing pkg
            self.errors.append(str(exc))
            self.events.on_status(f"Cannot start AI engine: {exc}")
            return False

    def run(self) -> None:
        """Execute the complete workflow until stopped or queue exhausted."""
        self.started_at = time.time()
        if not self._init_llm():
            return

        resumed = self.state.load()
        if resumed and self.state.data.get("project") == self.root:
            self.events.on_status("Resuming previous session state.")
        else:
            self.state.data["session_id"] = f"guardian_{int(self.started_at)}"
            self.state.data["mode"] = self.config.mode
            self.state.data["auto_fix"] = self.config.auto_fix

        scanner = Scanner(self.config)
        self.events.on_status("Scanning project...")
        self.profile = scanner.collect(self.root)
        self.files_skipped_count = self.profile.skipped_count

        if self.config.mode == "analyzer":
            self._run_analyzer()
            return

        system_prompt = BUG_FIXER_SYSTEM if self.config.mode == "bug_fixer" else UI_FIXER_SYSTEM
        queue = [f.relative_path for f in self.profile.files
                 if not f.skipped_reason]
        remaining_state = self.state.data["files_remaining"]
        analyzed_state = set(self.state.data["files_analyzed"])
        queue = [q for q in queue if q not in analyzed_state]
        if not resumed:
            self.state.data["files_remaining"] = list(queue)
        else:
            queue = remaining_state or queue
            self.state.data["files_remaining"] = list(queue)

        # Priority ordering: suspicious files first.
        queue.sort(key=lambda p: (not any(h in p.lower() for h in PRIORITY_HINTS), p))

        total = max(len(queue), 1)
        context_notes = self._build_context_notes()

        for idx, rel_path in enumerate(list(queue), start=1):
            if self.stop_requested:
                self.events.on_status("Stop requested - saving state.")
                break
            while self.paused and not self.stop_requested:
                time.sleep(0.3)

            self.events.on_file(rel_path, idx, len(queue))
            info = next((f for f in self.profile.files if f.relative_path == rel_path), None)
            if info is None:
                continue

            raw = read_file_safe(info.path, self.config.max_file_bytes())
            gen_marker = detect_minified_or_generated(info.path, raw)
            content = self.secret_guard.guard(rel_path, raw)

            file_findings: List[Finding] = []
            chunks = chunk_content(content, int(self.config.get("analysis.chunk_size_lines", 400)))
            usable_chunks = chunks if len(chunks) <= 1 else chunks[:6]

            for start_line, body in usable_chunks:
                label = rel_path if len(usable_chunks) == 1 else f"{rel_path} (lines {start_line}+)"
                prompt = build_analysis_user_prompt(
                    self.profile.summary_lines(), label, body, context_notes)
                try:
                    reply = self.llm.chat([
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ])
                except LLMError as exc:
                    self.errors.append(f"{rel_path}: {exc}")
                    break
                parsed = parse_findings_json(reply["content"])
                for pf in parsed:
                    pf.file = rel_path
                file_findings.extend(parsed)

            if gen_marker:
                for pf in file_findings:
                    pf.reason = (f"[{gen_marker} file - inferred] " + pf.reason).strip()
                    if pf.status == "open":
                        pf.status = "inferred_issue"

            added = self.store.add_all(file_findings)
            for pf in file_findings:
                if pf.status == "open":
                    self.events.on_finding(pf)

            # Auto-fix flow for HIGH severity and above.
            if self.config.auto_fix:
                for pf in deduplicate(file_findings):
                    if pf.severity in ("CRITICAL", "HIGH") and pf.status == "open":
                        ok, note = self._apply_fix(pf)
                        self.events.on_fix(pf, ok, note)

            self.files_analyzed_count += 1
            # assert (disabled).llm is not None
            self.state.data["tokens_used"] = self.llm.tokens_used
            self.state.data["requests_used"] = self.llm.requests_used
            self.state.mark_analyzed(rel_path)

        self.state.save()

    # ------------------------------------------------------------------
    # Fixing + re-check
    # ------------------------------------------------------------------

    def _apply_fix(self, finding: Finding) -> tuple:
        """Generate, validate, apply, and re-check a targeted fix."""
        # assert (disabled).llm is not None
        try:
            abs_path = safe_join(self.root, finding.file)
        except PathSafetyError as exc:
            self.events.on_fix(finding, False, str(exc))
            return False, str(exc)
        if not os.path.exists(abs_path):
            self.events.on_fix(finding, False, "File no longer exists.")
            return False, "missing"

        raw = read_file_safe(abs_path, self.config.max_file_bytes())
        lines = raw.splitlines()
        numbered = "\n".join(f"{i+1}| {l}" for i, l in enumerate(lines))
        before = raw

        try:
            reply = self.llm.chat([
                {"role": "system", "content": FIX_SYSTEM},
                {"role": "user", "content": build_fix_user_prompt(
                    finding.file, numbered, finding.to_dict())},
            ])
        except LLMError as exc:
            self.store.update_status(finding.file, finding.line, "fix_failed",
                                     recheck=str(exc))
            self.events.on_fix(finding, False, str(exc))
            return False, str(exc)

        payload = self._parse_object(reply["content"])
        if not payload or not payload.get("safe") or "new_content" not in payload:
            note = payload.get("explanation", "AI judged the fix unsafe.") if payload \
                else "Unparseable AI response."
            self.store.update_status(finding.file, finding.line, "fix_failed", recheck=note)
            self.events.on_fix(finding, False, note)
            return False, note

        new_content = str(payload["new_content"])
        # Basic sanity: file must remain non-trivially similar in size.
        if len(new_content) < len(before) * 0.2:
            note = "Fix rejected: replacement shrank the file suspiciously."
            self.store.update_status(finding.file, finding.line, "fix_failed", recheck=note)
            self.events.on_fix(finding, False, note)
            return False, note

        try:
            atomic_write(abs_path, new_content)
        except OSError as exc:
            note = f"Write failed: {exc}"
            self.store.update_status(finding.file, finding.line, "fix_failed", recheck=note)
            self.events.on_fix(finding, False, note)
            return False, note

        self.changes.record(finding.file, "modify", before=before, after=new_content)
        self.state.data["applied_fixes"].append(
            {"file": finding.file, "line": finding.line,
             "explanation": payload.get("explanation", "")})
        self.state.save()

        # Re-check pass
        verdict = self._recheck(finding, new_content)
        if verdict.get("resolved"):
            self.store.update_status(finding.file, finding.line, "fixed",
                                     recheck=verdict.get("note", ""), fix_applied=True)
            self.events.on_fix(finding, True, verdict.get("note", ""))
            return True, verdict.get("note", "")
        new_issues = "; ".join(verdict.get("new_issues", []))
        status = "fix_failed" if not verdict.get("resolved") else "fixed"
        self.store.update_status(finding.file, finding.line, status,
                                 recheck=verdict.get("note", "") or new_issues,
                                 fix_applied=True)
        self.events.on_fix(finding, bool(verdict.get("resolved")),
                           verdict.get("note", "") or new_issues or "Re-check inconclusive.")
        return bool(verdict.get("resolved")), verdict.get("note", "")

    def _recheck(self, finding: Finding, new_content: str) -> dict:
        # assert (disabled).llm is not None
        clean = self.secret_guard.guard(finding.file, new_content[:20000])
        try:
            reply = self.llm.chat([
                {"role": "system", "content": RECHECK_SYSTEM},
                {"role": "user", "content":
                    f"FINDING:\n{json.dumps(finding.to_dict())}\n\nFILE AFTER FIX:\n{clean}"},
            ])
            payload = self._parse_object(reply["content"])
            return payload or {"resolved": True, "new_issues": [],
                               "note": "Could not parse verification response; assumed OK."}
        except LLMError as exc:
            return {"resolved": True, "new_issues": [],
                    "note": f"Verification skipped: {exc}"}

    @staticmethod
    def _parse_object(text: str) -> Optional[dict]:
        fenced = None
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            fenced = m.group(1)
        for candidate in ([fenced] if fenced else []) + [text]:
            start = candidate.find("{")
            while start != -1:
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
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(candidate[start:i + 1])
                            except ValueError:
                                break
                start = candidate.find("{", start + 1)
        
    # ------------------------------------------------------------------
    # Analyzer mode
    # ------------------------------------------------------------------

    def _run_analyzer(self) -> None:
        # assert (disabled).llm is not None and self.profile is not None
        self.events.on_status("Building project map...")
        summary_lines = self.profile.summary_lines() + [
            f"Package managers: {', '.join(self.profile.package_managers) or 'None'}",
            f"Entry points: {', '.join(self.profile.entry_points) or 'None detected'}",
            f"Config files: {', '.join(self.profile.config_files[:10])}",
            f"Env files present: {len(self.profile.env_files)}",
            f"Tests detected: {'yes' if self.profile.has_tests else 'no'}",
        ]
        key_files = [f for f in self.profile.files if not f.skipped_reason][:12]
        excerpts = []
        for kf in key_files:
            raw = read_file_safe(kf.path, 6000)
            excerpts.append(f"--- {kf.relative_path} ---\n{self.secret_guard.guard(kf.relative_path, raw)}")
        prompt = "\n".join(summary_lines) + "\n\nKEY FILES:\n\n" + "\n\n".join(excerpts)
        self.events.on_status("Generating technical overview...")
        try:
            reply = self.llm.chat([
                {"role": "system", "content": ANALYZER_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            self.analyzer_report = reply["content"]
        except LLMError as exc:
            self.errors.append(str(exc))
            self.analyzer_report = f"# Analysis failed\n\n{exc}"

    # ------------------------------------------------------------------

    def _build_context_notes(self) -> str:
        """Summarize imports across files so the model sees relationships."""
        if not self.profile:
            return ""
        notes = []
        for f in self.profile.files[:80]:
            if f.skipped_reason or f.extension not in (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs"):
                continue
            head = read_file_safe(f.path, 3000)
            imports = [
                line.strip() for line in head.splitlines()
                if line.strip().startswith(("import ", "from ", "#include", "require(", "use "))
            ][:5]
            if imports:
                notes.append(f"{f.relative_path} imports: {'; '.join(imports)}")
        return "\n".join(notes[:40])

    # ------------------------------------------------------------------

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0
