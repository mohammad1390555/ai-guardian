# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Atomic file writes, change log, and path safety."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from typing import List


class PathSafetyError(Exception):
    """Raised when a path escapes the project root."""


def safe_join(project_root: str, relative_path: str) -> str:
    """Join and verify the result stays inside the project root."""
    root_abs = os.path.abspath(project_root)
    target = os.path.abspath(os.path.join(root_abs, relative_path))
    if not (target == root_abs or target.startswith(root_abs + os.sep)):
        raise PathSafetyError(f"Path escapes project root: {relative_path}")
    return target


def atomic_write(path: str, content: str) -> None:
    """Write file content atomically: temp file in same dir then rename."""
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".guardian_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    except OSError:
        if os.path.exists(tmp_path):
            # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # os.remove(tmp_path)
        raise


class ChangeLog:
    """Records every modification for rollback and audit."""

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self.entries: List[dict] = []
        self.log_path = os.path.join(project_root, ".guardian_changes.jsonl")

    def record(self, relative_path: str, action: str,
               before: str = "", after: str = "") -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "file": relative_path,
            "action": action,
            "before_bytes": len(before.encode("utf-8", errors="replace")),
            "after_bytes": len(after.encode("utf-8", errors="replace")),
            "before": before,
            "after": after,
        }
        self.entries.append(entry)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(entry.get("timestamp", "") + " | " + relative_path + " | "
                     + action + "\n")

    def rollback_last(self, scanner_reader) -> bool:
        """Undo the most recent change. Returns True on success."""
        if not self.entries:
            return False
        last = self.entries.pop()
        target = safe_join(self.project_root, last["file"])
        try:
            if last["action"] == "modify":
                atomic_write(target, last["before"])
                return True
        except OSError:
            return False
        return False
