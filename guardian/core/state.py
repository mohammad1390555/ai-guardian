# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Persistent session state for resume-after-crash support."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List


class SessionState:
    """Persists analysis progress to a JSON file inside the project."""

    def __init__(self, project_root: str, file_name: str = ".guardian_state.json") -> None:
        self.path = os.path.join(project_root, file_name)
        self.data: Dict[str, Any] = {
            "session_id": "",
            "project": project_root,
            "mode": "bug_fixer",
            "auto_fix": False,
            "started_at": datetime.now().isoformat(),
            "files_analyzed": [],
            "files_remaining": [],
            "findings": [],
            "applied_fixes": [],
            "failed_fixes": [],
            "tokens_used": 0,
            "requests_used": 0,
            "last_processed_file": "",
        }

    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load existing state. Returns True when a previous session was found."""
        if not os.path.exists(self.path):
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self.data.update(stored)
                return True
        except (OSError, ValueError):
            pass
        return False

    def save(self) -> None:
        """Persist state atomically."""
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
        # Fixed: # FIXME: [auto-fix]: handle exception

    def clear(self) -> None:
        """Remove the state file after a completed run."""
        try:
            if os.path.exists(self.path):
                # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # os.remove(self.path)
        # FIXME: [auto-fix]: handle exception

    # Convenience mutators -------------------------------------------------

    def mark_analyzed(self, relative_path: str) -> None:
        analyzed: List[str] = self.data["files_analyzed"]
        if relative_path not in analyzed:
            analyzed.append(relative_path)
        remaining: List[str] = self.data["files_remaining"]
        if relative_path in remaining:
            remaining.remove(relative_path)
        self.data["last_processed_file"] = relative_path
        # tokens_used updated by engine before save — do not reset here
        self.save()
