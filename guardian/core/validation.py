"""Technology-aware post-fix validation. Never runs destructive commands."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValidationResult:
    command: str
    ok: bool
    output: str


SAFE_COMMANDS = {
    "npm run build", "npm run lint", "npm test", "npm run test",
    "npx tsc --noEmit", "python -m pytest --co -q", "cargo check",
    "go build ./...", "make check", "composer validate",
}

DANGEROUS_MARKERS = ("rm ", "sudo", "del ", "format ", "mkfs", "shutdown",
                     "> /dev/", "curl |", "wget ", "chmod 777")


def discover_commands(project_root: str, config) -> List[str]:
    """Pick safe validation commands based on detected project files."""
    mapping = config.get("validation.commands_by_tech", {}) or {}
    commands: List[str] = []
    pkg_json = os.path.join(project_root, "package.json")

    def _has(marker: str) -> bool:
        return os.path.exists(os.path.join(project_root, marker))

    if _has("package.json") and "node" in mapping:
        # Only add build/lint if the scripts exist in package.json.
        try:
            import json
            with open(pkg_json, encoding="utf-8") as fh:
                scripts = json.load(fh).get("scripts", {})
            for base in ("npm run build", "npm run lint"):
                script = base.split()[-1]
                if script in scripts and base not in commands:
                    commands.append(base)
        except (OSError, ValueError):
            pass
    if _has("tsconfig.json") and "typescript" in mapping:
        commands.extend(mapping["typescript"])
    if (_has("pyproject.toml") or _has("requirements.txt")) and "python" in mapping:
        commands.extend(mapping["python"])
    if _has("Cargo.toml") and "rust" in mapping:
        commands.extend(mapping["rust"])
    if _has("go.mod") and "go" in mapping:
        commands.extend(mapping["go"])

    return [c for c in commands if is_safe_command(c)][:4]


def is_safe_command(command: str) -> bool:
    lowered = command.lower()
    return (lowered in SAFE_COMMANDS or lowered.startswith(("npm run build", "npm run lint"))) \
        and not any(m in lowered for m in DANGEROUS_MARKERS)


def run_validation(project_root: str, command: str,
                   timeout: int = 300) -> ValidationResult:
    """Execute one whitelisted validation command."""
    if not is_safe_command(command):
        return ValidationResult(command, False, "Command blocked by safety policy.")
    try:
        proc = subprocess.run(
            command, shell=True, cwd=project_root,
            capture_output=True, text=True, timeout=timeout,
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        if len(output) > 8000:
            output = output[:8000] + "\n... [truncated]"
        return ValidationResult(command, proc.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return ValidationResult(command, False, f"Timed out after {timeout}s.")
    except OSError as exc:
        return ValidationResult(command, False, f"Failed to run: {exc}")
