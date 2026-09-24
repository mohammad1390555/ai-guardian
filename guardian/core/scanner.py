# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""Filesystem scanner with filtering, binary detection, and project profiling."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".pdf",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".avi",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".exe", ".dll", ".so",
    ".dylib", ".class", ".jar", ".pyc", ".sqlite", ".db", ".wasm",
}

MINIFIED_HINTS = (".min.js", ".min.css", ".bundle.js", ".chunk.js")
GENERATED_MARKERS = ("@generated", "DO NOT EDIT", "auto-generated")

TECH_SIGNATURES = [
    ("Next.js", ["next.config.js", "next.config.mjs", "next.config.ts"]),
    ("Nuxt", ["nuxt.config.ts", "nuxt.config.js"]),
    ("React", []),
    ("Vue", []),
    ("Svelte", []),
    ("Angular", ["angular.json"]),
    ("Tailwind CSS", ["tailwind.config.js", "tailwind.config.ts"]),
    ("TypeScript", ["tsconfig.json"]),
    ("Vite", ["vite.config.ts", "vite.config.js"]),
    ("Webpack", ["webpack.config.js"]),
    ("Docker", ["Dockerfile", "docker-compose.yml"]),
    ("GitHub Actions", []),
    ("Django", []),
    ("Flask", []),
    ("FastAPI", []),
    ("Rust", ["Cargo.toml"]),
    ("Go", ["go.mod"]),
    ("Java", ["pom.xml", "build.gradle"]),
    ("Kotlin", []),
    ("Swift", ["Package.swift"]),
    ("PHP", ["composer.json"]),
    ("Ruby", ["Gemfile"]),
]


@dataclass
class ProjectFileInfo:
    """Metadata about a single scanned file."""

    path: str
    relative_path: str
    size_bytes: int
    extension: str
    is_binary: bool = False
    skipped_reason: Optional[str] = None
    content_hash: str = ""


@dataclass
class ProjectProfile:
    """Aggregated overview of a scanned project."""

    root: str
    name: str
    files: List[ProjectFileInfo] = field(default_factory=list)
    total_size_bytes: int = 0
    languages: Dict[str, int] = field(default_factory=dict)
    technologies: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    env_files: List[str] = field(default_factory=list)
    has_tests: bool = False
    skipped_count: int = 0

    def summary_lines(self) -> List[str]:
        """Return human-readable summary lines for the CLI."""
        detected = ", ".join(self.technologies) if self.technologies else "Unknown"
        top_langs = sorted(self.languages.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lang_str = ", ".join(f"{name} ({count})" for name, count in top_langs) or "None"
        return [
            f"Project: {self.name}",
            f"Path: {self.root}",
            f"Files: {len(self.files)} analyzed / {self.skipped_count} skipped",
            f"Size: {_human_size(self.total_size_bytes)}",
            f"Detected: {detected}",
            f"Languages: {lang_str}",
        ]


def _human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def looks_binary(path: str) -> bool:
    """Heuristic binary detection by null byte sniffing."""
    try:
        with open(path, "rb") as fh:
            return b"\x00" in fh.read(8192)
    # Fixed: except OSError:
        return True


class Scanner:
    """Walks a project tree and produces a filtered file inventory."""

    def __init__(self, config) -> None:
        self.config = config

    def _is_ignored_dir(self, dirname: str) -> bool:
        ignored = set(self.config.ignored_directories())
        return dirname in ignored

    def _is_ignored_file(self, filename: str) -> bool:
        for pattern in self.config.ignored_files():
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def collect(self, root: str) -> ProjectProfile:
        """Scan the project and build a profile."""
        profile = ProjectProfile(root=root, name=os.path.basename(os.path.abspath(root)) or root)
        max_bytes = self.config.max_file_bytes()
        depth_limit = int(self.config.get("analysis.scan_depth", 12))
        root_depth = root.rstrip(os.sep).count(os.sep)

        for dirpath, dirnames, filenames in os.walk(root):
            current_depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
            dirnames[:] = [d for d in dirnames if not self._is_ignored_dir(d)]
            if current_depth >= depth_limit:
                dirnames[:] = []

            for fname in sorted(filenames):
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                info = ProjectFileInfo(
                    path=full, relative_path=rel,
                    size_bytes=0, extension=os.path.splitext(fname)[1].lower(),
                )
                try:
                    info.size_bytes = os.path.getsize(full)
                except OSError as exc:
                    info.skipped_reason = f"unreadable: {exc}"
                    profile.files.append(info); profile.skipped_count += 1; continue

                if self._is_ignored_file(fname):
                    info.skipped_reason = "ignored pattern"; profile.skipped_count += 1; profile.files.append(info); continue
                if info.size_bytes > max_bytes:
                    info.skipped_reason = f"too large ({_human_size(info.size_bytes)})"; profile.skipped_count += 1; profile.files.append(info); continue
                if info.extension in BINARY_EXTENSIONS or fname in ("Dockerfile",):
                    info.is_binary = info.extension in BINARY_EXTENSIONS
                    if info.is_binary:
                        info.skipped_reason = "binary"; profile.skipped_count += 1; profile.files.append(info); continue

                info.content_hash = self._quick_hash(full)
                profile.total_size_bytes += info.size_bytes
                profile.files.append(info)

        self._detect_technologies(profile)
        self._classify(profile)
        return profile

    @staticmethod
    def _quick_hash(path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                h.update(fh.read(65536))
            return h.hexdigest()[:16]
        except OSError:
            return ""

    def _detect_technologies(self, profile: ProjectProfile) -> None:
        names = {f.relative_path for f in profile.files}
        lowered = {n.lower() for n in names}
        for tech, markers in TECH_SIGNATURES:
            if any(m.lower() in lowered for m in markers):
                profile.technologies.append(tech)

        pkg_json = os.path.join(profile.root, "package.json")
        deps: List[str] = []
        if os.path.exists(pkg_json):
            try:
                import json
                data = json.loads(open(pkg_json, encoding="utf-8").read())
                deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
            except (OSError, ValueError):
                pass
        for dep, tech in (("react", "React"), ("vue", "Vue"), ("svelte", "Svelte"),
                          ("tailwindcss", "Tailwind CSS"), ("express", "Express"),
                          ("next", "Next.js")):
            if dep in deps and tech not in profile.technologies:
                profile.technologies.append(tech)

        if os.path.exists(os.path.join(profile.root, "package.json")):
            profile.package_managers.append("npm")
        if any(n.endswith(("yarn.lock",)) for n in names):
            profile.package_managers.append("yarn")
        if any(n.endswith(("pnpm-lock.yaml",)) for n in names):
            profile.package_managers.append("pnpm")
        if os.path.exists(os.path.join(profile.root, "pyproject.toml")) or \
           os.path.exists(os.path.join(profile.root, "requirements.txt")):
            profile.package_managers.append("pip/poetry")

        # Language counts from extensions
        ext_to_lang = {
            ".py": "Python", ".js": "JavaScript", ".jsx": "React JSX",
            ".ts": "TypeScript", ".tsx": "React TSX", ".html": "HTML",
            ".css": "CSS", ".scss": "SCSS", ".vue": "Vue", ".svelte": "Svelte",
            ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
            ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".swift": "Swift",
            ".sql": "SQL", ".sh": "Shell",
        }
        for f in profile.files:
            if f.skipped_reason:
                continue
            lang = ext_to_lang.get(f.extension)
            if lang:
                profile.languages[lang] = profile.languages.get(lang, 0) + 1

    def _classify(self, profile: ProjectProfile) -> None:
        """Flag entry points, configs, env files, and test presence."""
        entry_names = {"main.py", "app.py", "manage.py", "index.js", "main.js",
                       "index.ts", "server.js", "app.js", "wsgi.py", "asgi.py"}
        config_names = {"package.json", "tsconfig.json", "webpack.config.js",
                        "vite.config.ts", "pyproject.toml", "setup.py",
                        "Makefile", "Dockerfile", "docker-compose.yml",
                        "Cargo.toml", "go.mod", ".eslintrc.json"}
        for f in profile.files:
            base = os.path.basename(f.relative_path)
            if base in entry_names and len(profile.entry_points) < 10:
                profile.entry_points.append(f.relative_path)
            elif base in config_names:
                profile.config_files.append(f.relative_path)
            elif base.startswith(".env") or base.endswith((".env",)):
                profile.env_files.append(f.relative_path)
            if "/test" in f"/{f.relative_path.lower().rsplit('/', 1)[0]}" or \
               base.startswith("test_") or base.endswith("_test.go") or \
               base.endswith(".test.js") or base.endswith(".test.ts") or base.endswith(".spec.ts"):
                profile.has_tests = True


def read_file_safe(path: str, max_bytes: int) -> str:
    """Read text content safely with truncation marker."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read(max_bytes)
            rest = fh.read(1)
            if rest:
                data += "\n... [truncated by AI Guardian] ..."
            return data
    except OSError as exc:
        return f"// UNREADABLE: {exc}"


def chunk_content(content: str, chunk_size_lines: int = 400) -> List[tuple]:
    """Split content into (start_line, text) chunks preserving line numbers."""
    lines = content.splitlines()
    chunks = []
    for start in range(0, len(lines), chunk_size_lines):
        end = min(start + chunk_size_lines, len(lines))
        body = "\n".join(f"{i + start + 1}| {lines[i + start]}" for i in range(end - start))
        chunks.append((start + 1, body))
    if not chunks:
        chunks.append((1, ""))
    return chunks


def detect_minified_or_generated(path: str, content: str) -> Optional[str]:
    """Return a reason string when the file looks generated/minified."""
    base = os.path.basename(path).lower()
    if any(base.endswith(h) for h in MINIFIED_HINTS):
        return "minified"
    head = content[:4000]
    for marker in GENERATED_MARKERS:
        if marker.lower() in head.lower():
            return "generated"
    avg_len = sum(len(l) for l in content.splitlines()) / max(len(content.splitlines()), 1)
    if avg_len > 500:
        return "likely minified"
    