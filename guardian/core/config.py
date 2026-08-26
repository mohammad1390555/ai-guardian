"""Configuration loading, validation, and persistence for AI Guardian.

All settings live in a single JSON file (guardian.json by default).
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "deepseek-ai/deepseek-v4-flash-0731",
        "api_key_env": "NVIDIA_API_KEY",
    },
    "generation": {
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 16384,
        "reasoning": {"enabled": True, "effort": "high"},
        "stream": False,
        "request_timeout": 300,
    },
    "analysis": {
        "mode": "bug_fixer",          # bug_fixer | ui_fixer | analyzer
        "auto_fix": False,
        "continuous": True,
        "scan_depth": 12,             # max directory depth
        "chunk_size_lines": 400,
        "max_context_chars": 60000,
    },
    "backup": {
        "enabled": True,
        "directory": ".backups",
        "max_project_size_mb": 500,
    },
    "scanner": {
        "ignored_directories": [
            ".git", ".hg", ".svn", "node_modules", ".venv", "venv",
            "__pycache__", ".pytest_cache", ".mypy_cache", "dist",
            "build", ".next", ".nuxt", ".cache", "coverage", "vendor",
            "target", ".gradle", ".idea", ".vscode", "out", ".tox",
        ],
        "ignored_files": [
            "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "poetry.lock", "*.min.js", "*.min.css", "*.map", "*.pyc",
            "*.class", "*.jar", "*.so", "*.dylib", "*.dll", "*.exe",
            "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.webp",
            "*.woff", "*.woff2", "*.ttf", "*.eot", "*.mp4", "*.mp3",
            "*.zip", "*.tar.gz", "*.pdf", "*.sqlite", "*.db",
        ],
        "max_file_size_mb": 5,
        "text_extensions": [
            ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss",
            ".less", ".vue", ".svelte", ".json", ".yaml", ".yml", ".toml",
            ".ini", ".cfg", ".env.example", ".md", ".txt", ".sh", ".bash",
            ".sql", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c",
            ".cpp", ".h", ".hpp", ".cs", ".swift", ".dart", ".lua",
            ".xml", ".graphql", ".prisma", ".dockerfile", ".gitignore",
        ],
    },
    "validation": {
        "enabled": True,
        "commands_by_tech": {
            "node": ["npm run build --if-present", "npm run lint --if-present"],
            "typescript": ["npx tsc --noEmit"],
            "python": ["python -m pytest --co -q"],
            "rust": ["cargo check"],
            "go": ["go build ./..."],
        },
    },
    "reports": {"directory": "reports"},
    "state": {"file": ".guardian_state.json"},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base and return a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigError(Exception):
    """Raised when the configuration file is invalid."""


@dataclass
class Config:
    """Validated application configuration."""

    data: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CONFIG))
    path: str = ""

    # ------------------------------------------------------------------
    # Loading / saving
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        """Load config from JSON file, merging over defaults."""
        cfg = cls()
        if path:
            cfg.path = path
        else:
            cfg.path = os.path.join(os.getcwd(), "guardian.json")
        if os.path.exists(cfg.path):
            try:
                with open(cfg.path, "r", encoding="utf-8") as fh:
                    user_data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Invalid JSON in {cfg.path}: {exc}") from exc
            if not isinstance(user_data, dict):
                raise ConfigError(f"Top level of {cfg.path} must be a JSON object.")
            cfg.data = _deep_merge(DEFAULT_CONFIG, user_data)
        cfg._validate()
        return cfg

    def save(self, path: str | None = None) -> None:
        """Persist current settings to disk."""
        target = path or self.path or os.path.join(os.getcwd(), "guardian.json")
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        mode = self.get("analysis.mode")
        if mode not in ("bug_fixer", "ui_fixer", "analyzer"):
            raise ConfigError(
                f"analysis.mode must be one of bug_fixer, ui_fixer, analyzer (got '{mode}')"
            )
        max_mb = self.get("scanner.max_file_size_mb")
        if not isinstance(max_mb, (int, float)) or max_mb <= 0:
            raise ConfigError("scanner.max_file_size_mb must be a positive number.")

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @property
    def api_key_env(self) -> str:
        return str(self.get("provider.api_key_env", ""))

    def resolve_api_key(self) -> str:
        """Read the API key from the configured environment variable."""
        env_name = self.api_key_env
        value = os.environ.get(env_name, "")
        if not value:
            raise ConfigError(
                f"API key environment variable '{env_name}' is not set. "
                f"Export it before running analysis."
            )
        return value

    @property
    def mode(self) -> str:
        return str(self.get("analysis.mode"))

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("bug_fixer", "ui_fixer", "analyzer"):
            raise ConfigError(f"Unknown mode '{value}'.")
        self.set("analysis.mode", value)

    @property
    def auto_fix(self) -> bool:
        return bool(self.get("analysis.auto_fix"))

    @auto_fix.setter
    def auto_fix(self, value: bool) -> None:
        self.set("analysis.auto_fix", bool(value))

    def ignored_directories(self) -> List[str]:
        return list(self.get("scanner.ignored_directories", []))

    def ignored_files(self) -> List[str]:
        return list(self.get("scanner.ignored_files", []))

    def max_file_bytes(self) -> int:
        return int(float(self.get("scanner.max_file_size_mb", 5)) * 1024 * 1024)
