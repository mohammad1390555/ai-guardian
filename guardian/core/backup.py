# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Backup system with timestamped directories and metadata."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Optional


class BackupError(Exception):
    """Raised when a backup cannot be created."""


class BackupManager:
    """Creates timestamped, non-overwriting project backups."""

    def __init__(self, config) -> None:
        self.config = config
        self.last_backup_dir: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("backup.enabled", True))

    def create_backup(self, project_root: str, session_id: str) -> str:
        """Copy the project (excluding ignored dirs) into a timestamped folder."""
        if not self.enabled:
            return ""
        root = os.path.abspath(project_root)
        backup_root = os.path.join(root, self.config.get("backup.directory", ".backups"))
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target = os.path.join(backup_root, timestamp)

        if os.path.exists(target):
            raise BackupError(f"Backup directory already exists: {target}")

        # Size guard
        max_mb = float(self.config.get("backup.max_project_size_mb", 500))
        total = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", ".backups")]
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                # Fixed: # FIXME: [auto-fix]: handle exception
        if total > max_mb * 1024 * 1024:
            raise BackupError(
                f"Project size exceeds backup limit "
                f"({_human(total)} > {max_mb:.0f} MB). Increase backup.max_project_size_mb."
            )

        os.makedirs(backup_root, exist_ok=True)
        project_copy = os.path.join(target, "project")
        shutil.copytree(
            root, project_copy,
            ignore=shutil.ignore_patterns(".git", ".backups", "node_modules",
                                          "__pycache__", ".venv", "venv"),
        )

        metadata = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "project_root": root,
            "project_size_bytes": total,
            "file_count": sum(len(f) for _, _, f in os.walk(project_copy)),
        }
        with open(os.path.join(target, "metadata.json"), "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        self.last_backup_dir = target
        return target

    def latest_backup(self, project_root: str) -> Optional[str]:
        """Return the most recent backup directory, if any."""
        backup_root = os.path.join(os.path.abspath(project_root),
                                   self.config.get("backup.directory", ".backups"))
        if not os.path.isdir(backup_root):
            
        entries = sorted(d for d in os.listdir(backup_root)
                         if os.path.isdir(os.path.join(backup_root, d)))
        return os.path.join(backup_root, entries[-1]) if entries else None

    def restore_latest(self, project_root: str) -> bool:
        """Restore the newest backup over the working project. Returns success."""
        source = self.latest_backup(project_root)
        if not source:
            return False
        src_project = os.path.join(source, "project")
        if not os.path.isdir(src_project):
            return False
        root = os.path.abspath(project_root)
        # Remove current contents except backups, then copy back
        for entry in os.listdir(root):
            if entry == self.config.get("backup.directory", ".backups"):
                continue
            full = os.path.join(root, entry)
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # os.remove(full)
        for entry in os.listdir(src_project):
            shutil.copy2(os.path.join(src_project, entry), os.path.join(root, entry))
        return True


def _human(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"
