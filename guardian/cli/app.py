"""AI Guardian interactive CLI built with Rich."""

from __future__ import annotations

import os
import sys
import time
from typing import List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, IntPrompt
    from rich.text import Text
    from rich.live import Live
except ImportError:  # pragma: no cover
    print("Missing dependency 'rich'. Install with: pip install rich")
    sys.exit(1)

from guardian.core.config import Config, ConfigError
from guardian.core.scanner import Scanner
from guardian.core.backup import BackupManager, BackupError
from guardian.core.findings import SEVERITY_ORDER
from guardian.core.validation import discover_commands, run_validation
from guardian.core.reports import ReportGenerator
from guardian.analysis.engine import AnalysisEngine, EngineEvent

console = Console()

BANNER = r"""
   ___   __ _    _    _   _ ___
  / _ \ / _| |  / \  | \ | |_ _|
 | (_) | |_| | / _ \ |  \| || |
  \__, |  _| |/ ___ \| |\  || |
    /_/|_| |_/_/   \_\_| \_|___|
      Intelligent Code & UI Analysis
"""

SEVERITY_STYLES = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "cyan",
    "INFO": "dim",
}

COMMANDS_HELP = """[bold]Commands[/bold]
  help          Show this help
  status        Show session status panel
  scan          Start (or resume) continuous analysis
  pause         Pause the running analysis
  resume        Resume a paused analysis
  fix           Fix all open HIGH/CRITICAL findings now (requires auto fix)
  findings      List current findings
  report        Generate Markdown + JSON report
  history       Show applied changes and fixes
  config        Show or change configuration (e.g. `config set analysis.auto_fix true`)
  mode          Switch mode: bug_fixer / ui_fixer / analyzer
  validate      Run detected validation commands
  rollback      Undo the most recent file change
  clear         Clear the screen
  exit          Save state and quit"""


class GuardianCLI:
    """Main application loop."""

    def __init__(self) -> None:
        self.config: Optional[Config] = None
        self.project_root: str = ""
        self.engine: Optional[AnalysisEngine] = None
        self.backup_manager: Optional[BackupManager] = None
        self.backup_dir: str = ""
        self.profile = None
        self.last_validation: list = []

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def run(self) -> None:
        console.print(Text(BANNER, style="bold blue"), justify="center")
        console.print(Panel(
            "[bold blue]AI PROJECT GUARDIAN[/bold blue]\n"
            "Intelligent Code & UI Analysis",
            border_style="blue", expand=False))
        console.print()

        self.config = self._load_config()
        self._select_project()
        self._show_project_summary()
        self._command_loop()

    def _load_config(self) -> Config:
        try:
            return Config.load()
        except ConfigError as exc:
            console.print(f"[red]Configuration error:[/red] {exc}")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Project selection
    # ------------------------------------------------------------------

    def _select_project(self) -> None:
        while True:
            console.print("[bold]Project Selection[/bold]")
            console.print("  1. Enter a project path")
            console.print("  2. Use current directory")
            console.print("  3. Browse directories\n")
            choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="2")

            if choice == "1":
                path = Prompt.ask("Project path").strip()
            elif choice == "2":
                path = os.getcwd()
            else:
                path = self._browse(os.getcwd())

            path = os.path.abspath(os.path.expanduser(path))
            if not os.path.isdir(path):
                console.print(f"[red]Not a directory:[/red] {path}\n")
                continue
            if os.path.basename(path) in (".git",):
                console.print("[red]Please select a project directory, not .git[/red]\n")
                continue

            self.project_root = path
            self.config.path = os.path.join(path, "guardian.json")
            if not os.path.exists(self.config.path):
                self.config.save(self.config.path)
                console.print(f"[green]Created default config:[/green] {self.config.path}")
            try:
                self.config = Config.load(self.config.path)
            except ConfigError as exc:
                console.print(f"[red]Config error:[/red] {exc}\n")
                continue

            mode_names = {"bug_fixer": "Bug Fixer", "ui_fixer": "UI Fixer",
                          "analyzer": "Project Analyzer"}
            console.print(f"\nMode is [bold]{mode_names[self.config.mode]}[/bold]. "
                          f"Change it? (bug_fixer / ui_fixer / analyzer / enter to keep)")
            new_mode = Prompt.ask("Mode", default=self.config.mode)
            if new_mode in ("bug_fixer", "ui_fixer", "analyzer"):
                self.config.mode = new_mode
                self.config.save()
            break

    def _browse(self, start: str) -> str:
        current = start
        while True:
            try:
                entries = sorted(
                    d for d in os.listdir(current)
                    if os.path.isdir(os.path.join(current, d)) and not d.startswith("."))
            except OSError:
                entries = []
            console.print(f"\n[bold]{current}[/bold]")
            for i, name in enumerate(entries[:20], 1):
                console.print(f"  {i}. {name}/")
            console.print("  ..  parent directory")
            pick = Prompt.ask("Pick number, '..' to go up, or 's' to select this folder",
                              default="s")
            if pick == "s":
                return current
            if pick == "..":
                current = os.path.dirname(current) or "/"
                continue
            if pick.isdigit() and 1 <= int(pick) <= len(entries[:20]):
                current = os.path.join(current, entries[int(pick) - 1])
                continue
            console.print("[red]Invalid choice.[/red]")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _show_project_summary(self) -> None:
        assert self.config is not None
        console.print("\n[bold]Building project summary...[/bold]")
        profile = Scanner(self.config).collect(self.project_root)
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold blue]Project:[/bold blue]", profile.name)
        table.add_row("[bold blue]Path:[/bold blue]", profile.root)
        table.add_row("[bold green]Files:[/bold green]",
                      f"{len(profile.files) - profile.skipped_count} analyzable "
                      f"/ {profile.skipped_count} skipped")
        size_mb = profile.total_size_bytes / (1024 * 1024)
        table.add_row("[bold green]Size:[/bold green]", f"{size_mb:.1f} MB")
        table.add_row("[bold cyan]Detected:[/bold cyan]",
                      ", ".join(profile.technologies) or "Unknown stack")
        mode_names = {"bug_fixer": "Bug Fixer", "ui_fixer": "UI Fixer",
                      "analyzer": "Project Analyzer"}
        table.add_row("[bold magenta]Mode:[/bold magenta]", mode_names[self.config.mode])
        af = "[green]ENABLED[/green]" if self.config.auto_fix else "[red]DISABLED[/red]"
        table.add_row("Auto Fix:", af)
        console.print(table)
        self.profile = profile

    # ------------------------------------------------------------------
    # Command loop
    # ------------------------------------------------------------------

    def _ensure_engine(self) -> bool:
        if self.engine is not None:
            return True
        try:
            self.engine = AnalysisEngine(self.config, self.project_root,
                                         events=EngineEvent(
                                             on_file=self._render_file_progress,
                                             on_finding=self._render_finding,
                                             on_fix=self._render_fix,
                                             on_status=self._render_status))
        except Exception as exc:  # missing API key etc.
            console.print(f"[red]Cannot initialize engine:[/red] {exc}")
            return False
        return True

    def _maybe_backup(self) -> bool:
        self.backup_manager = BackupManager(self.config)
        if not self.backup_manager.enabled:
            return True
        try:
            with console.status("Creating project backup...", spinner="dots"):
                self.backup_dir = self.backup_manager.create_backup(
                    self.project_root, f"guardian_{int(time.time())}")
            console.print(f"[green]Backup created:[/green] {self.backup_dir}")
            return True
        except BackupError as exc:
            ok = console.input(f"[yellow]{exc} Continue without backup? (y/N) [/yellow]")
            return ok.strip().lower() == "y"

    def _command_loop(self) -> None:
        console.print("\nType 'help' for commands.\n")
        while True:
            try:
                raw = Prompt.ask("[bold blue]guardian[/bold blue]").strip()
            except (EOFError, KeyboardInterrupt):
                raw = "exit"
            if not raw:
                continue
            parts = raw.split()
            cmd, args = parts[0].lower(), parts[1:]
            handler = getattr(self, f"_cmd_{cmd}", None)
            known = {"help", "status", "scan", "pause", "resume", "fix", "findings",
                     "report", "history", "config", "mode", "validate", "rollback",
                     "clear", "exit", "quit"}
            if cmd == "help":
                console.print(COMMANDS_HELP)
            elif handler:
                result = handler(args)
                if result == "EXIT":
                    break
            elif cmd in ("quit", "q"):
                self._save_and_exit()
                break
            else:
                console.print(f"[red]Unknown command:[/red] {cmd}. Type 'help'.")

    def _save_and_exit(self) -> None:
        if self.engine:
            self.engine.request_stop()
            self.engine.state.save()
        console.print("[green]Session state saved. Goodbye.[/green]")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_scan(self, args) -> None:
        if not self._ensure_engine():
            return
        if not self._maybe_backup():
            return
        console.print("[bold blue]Starting continuous analysis. "
                      "Use 'pause', 'resume', or 'exit' to control it.[/bold blue]\n")
        try:
            self.engine.run()
        except KeyboardInterrupt:
            self.engine.request_stop()
            self.engine.state.save()
            console.print("\n[yellow]Interrupted - progress saved.[/yellow]")
        self._print_run_summary()

    def _print_run_summary(self) -> None:
        e = self.engine
        fixed = sum(1 for f in e.store.findings if f.status == "fixed")
        open_count = sum(1 for f in e.store.findings if f.status == "open")
        console.print(Panel(
            f"Files analyzed: {e.files_analyzed_count}\n"
            f"Findings total: {len(e.store.findings)}\n"
            f"Fixed: [green]{fixed}[/green]\n"
            f"Still open: [yellow]{open_count}[/yellow]\n"
            f"Tokens used: {getattr(e.llm, 'tokens_used', 0)}\n"
            f"Notepad: {os.path.join(e.root, '.guardian_findings.md')}",
            title="[bold blue]Run Complete[/bold blue]", border_style="blue"))

    def _cmd_pause(self, args) -> None:
        if self.engine:
            self.engine.paused = True
            console.print("[yellow]Paused after the current file.[/yellow]")

    def _cmd_resume(self, args) -> None:
        if self.engine:
            self.engine.paused = False
            console.print("[green]Resumed.[/green]")

    def _cmd_status(self, args) -> None:
        if not self.engine:
            console.print("[dim]No session yet. Run 'scan' first.[/dim]")
            return
        e = self.engine
        remaining = len(e.state.data.get("files_remaining", []))
        analyzed = len(e.state.data.get("files_analyzed", []))
        console.print(Panel(
            f"Project: {self.project_root}\n"
            f"Mode: {self.config.mode}\n"
            f"Auto Fix: {'ON' if self.config.auto_fix else 'OFF'}\n"
            f"Files analyzed: {analyzed}\n"
            f"Files remaining: {remaining}\n"
            f"Findings: {len(e.store.findings)}\n"
            f"Tokens used: {getattr(e.llm, 'tokens_used', 0)}\n"
            f"Requests used: {getattr(e.llm, 'requests_used', 0)}\n"
            f"Paused: {'yes' if e.paused else 'no'}",
            title="[bold blue]Status[/bold blue]", border_style="blue"))

    def _cmd_findings(self, args) -> None:
        if not self.engine or not self.engine.store.findings:
            console.print("[dim]No findings yet.[/dim]")
            return
        table = Table(title="Findings", border_style="blue")
        table.add_column("Severity", max_width=9)
        table.add_column("File", max_width=42)
        table.add_column("Line", justify="right")
        table.add_column("Conf.", justify="right")
        table.add_column("Category")
        table.add_column("Status")
        for f in sorted(self.engine.store.findings, key=lambda x: x.sort_key()):
            style = SEVERITY_STYLES.get(f.severity, "")
            conf = f"{int(f.confidence * 100)}%"
            status_color = {"fixed": "green", "fix_failed": "red"}.get(f.status, "")
            table.add_row(Text(f.severity, style=style), f.file, str(f.line),
                          conf, f.category,
                          Text(f.status, style=status_color))
        console.print(table)

    def _cmd_fix(self, args) -> None:
        if not self._ensure_engine():
            return
        if not self.engine.llm and hasattr(self.engine, "_init_llm"):
            if not self.engine._init_llm():
                return
        if not self.config.auto_fix:
            confirm = console.input(
                "[yellow]Auto Fix is OFF. Enable it for this run? (y/N) [/yellow]")
            if confirm.strip().lower() != "y":
                return
            self.config.auto_fix = True
        targets = [f for f in self.engine.store.findings
                   if f.status == "open" and f.severity in ("CRITICAL", "HIGH")]
        if not targets:
            console.print("[green]No open CRITICAL/HIGH findings to fix.[/green]")
            return
        console.print(f"[bold]Fixing {len(targets)} high-severity finding(s)...[/bold]")
        for f in targets:
            ok, note = self.engine._apply_fix(f)
            style = "green" if ok else "red"
            console.print(f"[{style}]{'FIXED' if ok else 'FAILED'}[/{style}] "
                          f"{f.file}:{f.line} - {note}")

    def _cmd_report(self, args) -> None:
        if not self.engine:
            console.print("[dim]Nothing to report yet. Run 'scan' first.[/dim]")
            return
        gen = ReportGenerator(self.project_root, self.config)
        md_path, json_path = gen.generate(self.engine, self.last_validation or [])
        console.print(f"[green]Markdown report:[/green] {md_path}")
        console.print(f"[green]JSON report:[/green] {json_path}")

    def _cmd_validate(self, args) -> None:
        cmds = discover_commands(self.project_root, self.config)
        if not cmds:
            console.print("[dim]No safe validation commands detected for this project.[/dim]")
            return
        results = []
        for c in cmds:
            with console.status(f"Running: {c}", spinner="dots"):
                vr = run_validation(self.project_root, c)
            results.append(vr)
            style = "green" if vr.ok else "red"
            console.print(f"[{style}]{'PASS' if vr.ok else 'FAIL'}[/{style}] {c}")
        self.last_validation = results

    def _cmd_history(self, args) -> None:
        log_path = os.path.join(self.project_root, ".guardian_changes.jsonl")
        if not os.path.exists(log_path):
            console.print("[dim]No changes recorded.[/dim]")
            return
        with open(log_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        console.print(f"[bold]{len(lines)} recorded change(s):[/bold]")
        for line in lines[-20:]:
            console.print(f"  {line.rstrip()}")

    def _cmd_rollback(self, args) -> None:
        if not self.engine or not self.engine.changes.entries:
            console.print("[dim]Nothing to roll back.[/dim]")
            return
        if self.engine.changes.rollback_last(None):
            console.print("[green]Rolled back the last file change.[/green]")
        else:
            console.print("[red]Rollback failed.[/red]")

    def _cmd_config(self, args) -> None:
        if not args:
            import json as _json
            console.print(_json.dumps(self.config.data, indent=2))
            return
        if args[0] == "set" and len(args) >= 3:
            key, value = args[1], " ".join(args[2:])
            parsed: object = value
            if value.lower() in ("true", "false"):
                parsed = value.lower() == "true"
            elif value.replace(".", "", 1).isdigit():
                parsed = float(value) if "." in value else int(value)
            try:
                self.config.set(key, parsed)
                self.config._validate()
                self.config.save()
                console.print(f"[green]Saved:[/green] {key} = {parsed}")
            except ConfigError as exc:
                console.print(f"[red]{exc}[/red]")
        else:
            console.print("Usage: config set <dotted.key> <value>")

    def _cmd_mode(self, args) -> None:
        modes = ["bug_fixer", "ui_fixer", "analyzer"]
        target = args[0] if args else Prompt.ask("Mode", choices=modes,
                                                 default=self.config.mode)
        if target not in modes:
            console.print(f"[red]Unknown mode '{target}'.[/red]")
            return
        self.config.mode = target
        self.config.save()
        self.engine = None  # force engine rebuild with the new mode
        console.print(f"[green]Mode set to {target}. Run 'scan' to apply.[/green]")

    def _cmd_clear(self, args) -> None:
        console.clear()

    def _cmd_exit(self, args) -> None:
        self._save_and_exit()
        return "EXIT"

    # ------------------------------------------------------------------
    # Event renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_file_progress(path: str, idx: int, total: int) -> None:
        pct = int(idx * 100 / max(total, 1))
        filled = int(pct / 5)
        bar = "#" * filled + "-" * (20 - filled)
        console.print(f"\n[cyan][{bar:<20}] {pct}%[/cyan] ({idx}/{total})")
        console.print(f"[dim]Analyzing:[/dim] {path}")

    @staticmethod
    def _render_finding(finding) -> None:
        style = SEVERITY_STYLES.get(finding.severity, "")
        console.print(f"  [{style}]FINDING [{finding.severity}][/{style}] "
                      f"{finding.file}:{finding.line} - {finding.category}")
        console.print(f"  [dim]{finding.description}[/dim]")

    @staticmethod
    def _render_fix(finding, ok: bool, note: str) -> None:
        style = "green" if ok else "red"
        label = "FIX APPLIED" if ok else "FIX FAILED"
        console.print(f"  [{style}]{label}[/{style}] {finding.file}:{finding.line}"
                      + (f" - {note}" if note else ""))

    @staticmethod
    def _render_status(text: str) -> None:
        console.print(f"[bold blue]>[/bold blue] {text}")


def main() -> None:
    cli = GuardianCLI()
    cli.last_validation = []
    try:
        cli.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
