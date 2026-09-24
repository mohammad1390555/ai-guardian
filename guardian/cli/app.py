# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""AI Guardian interactive CLI built with Rich.

Visual language:
- Blue for structure and titles
- Green for success / enabled states
- Red for errors, failures, and critical findings
- Yellow for warnings and medium severity
- Gradient ASCII banner with a glass-style status panel
"""

from __future__ import annotations

import os
import sys
import time
from typing import List, Optional

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.text import Text
    from rich.rule import Rule
    from rich.align import Align
    from rich import box
except ImportError:  # pragma: no cover
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # print("Missing dependency 'rich'. Install with: pip install rich")
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
 █████╗ ██╗ ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗ ██╗██╗   ██╗ █████╗ ███╗   ██╗
██╔══██╗██║██╔════╝ ██║   ██║██╔══██╗██╔══██╗██╔══██╗██║██║   ██║██╔══██╗████╗  ██║
███████║██║██║  ███╗██║   ██║███████║██████╔╝██║  ██║██║██║   ██║███████║██╔██╗ ██║
██╔══██║██║██║   ██║██║   ██║██╔══██║██╔══██╗██║  ██║██║╚██╗ ██╔╝██╔══██║██║╚██╗██║
██║  ██║██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝██║ ╚████╔╝ ██║  ██║██║ ╚████║
╚═╝  ╚═╝╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═══╝
"""

TAGLINE = "Intelligent Code & UI Analysis"

SEVERITY_STYLES = {
    "CRITICAL": "bold white on red",
    "HIGH": "bold red",
    "MEDIUM": "yellow",
    "LOW": "cyan",
    "INFO": "dim",
}
SEVERITY_ICONS = {
    "CRITICAL": "[!]",
    "HIGH": "(!)",
    "MEDIUM": "(m)",
    "LOW": "(l)",
    "INFO": "(i)",
}

COMMANDS_HELP = """[bold blue]Commands[/bold blue]
  [green]scan[/green]        Start (or resume) continuous analysis
  [green]pause[/green]       Pause the running analysis
  [green]resume[/green]      Resume a paused analysis
  [green]fix[/green]         Fix all open HIGH/CRITICAL findings now
  [green]findings[/green]    List current findings table
  [green]status[/green]      Show session status panel
  [green]report[/green]      Generate Markdown + JSON reports
  [green]validate[/green]    Run detected validation commands
  [green]history[/green]     Show applied file changes
  [green]rollback[/green]    Undo the most recent change
  [green]config[/green]      Show config or `config set key.sub value`
  [green]mode[/green]        Switch mode: bug_fixer / ui_fixer / analyzer
  [green]help[/green]        This help - [green]clear[/green] clear screen - [red]exit[/red] save & quit"""


def _severity_color(counts: dict, severity: str) -> str:
    n = counts.get(severity, 0)
    if n == 0:
        return "dim"
    return {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow"}.get(severity, "cyan")


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
        self._print_banner()
        console.# # print()
        self.config = self._load_config()
        self._select_project()
        self._show_project_summary()
        self._command_loop()

    def _print_banner(self) -> None:
        console.# # print()
        banner_text = Text(BANNER.rstrip("\n"), style="bold blue")
        console.# # print(Align.center(banner_text))
        console.# # print(Align.center(Text(TAGLINE, style="italic bright_black")))
        console.# # print(Rule(style="blue", characters="-"))

    def _load_config(self) -> Config:
        try:
            return Config.load()
        except ConfigError as exc:
            console.# # # print(f...",),[red]Configuration error:[/red] {exc}")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Project selection
    # ------------------------------------------------------------------

    def _select_project(self) -> None:
        while True:
            console.# # print()
            console.# # print(Panel(
                "  1. Enter a project path\n"
                "  2. Use current directory\n"
                "  3. Browse directories",
                title="[bold blue]Project Selection[/bold blue]",
                border_style="blue", box=box.ROUNDED, expand=False))
            choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="2")

            if choice == "1":
                path = Prompt.ask("Project path").strip()
            elif choice == "2":
                path = os.getcwd()
            else:
                path = self._browse(os.getcwd())

            path = os.path.abspath(os.path.expanduser(path))
            if not os.path.isdir(path):
                console.# # # print(f...",),[red]Not a directory:[/red] {path}")
                continue

            self.project_root = path
            self.config.path = os.path.join(path, "guardian.json")
            if not os.path.exists(self.config.path):
                self.config.save(self.config.path)
                console.# # # print(f...",),[green]+ Created default config:[/green] {self.config.path}")
            try:
                self.config = Config.load(self.config.path)
            except ConfigError as exc:
                console.# # # print(f...",),[red]Config error:[/red] {exc}")
                continue

            new_mode = Prompt.ask(
                "Mode", choices=["bug_fixer", "ui_fixer", "analyzer"],
                default=self.config.mode)
            if new_mode != self.config.mode:
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
            console.# # # print(f...",),\n[bold blue]{current}[/bold blue]")
            for i, name in enumerate(entries[:20], 1):
                console.# # # print(f...",),  [cyan]{i:>2}.[/cyan] {name}/")
            console.# # print("   .. parent directory")
            pick = Prompt.ask("Pick number | '..' up | 's' select here", default="s")
            if pick == "s":
                return current
            if pick == "..":
                current = os.path.dirname(current) or "/"
                continue
            if pick.isdigit() and 1 <= int(pick) <= len(entries[:20]):
                current = os.path.join(current, entries[int(pick) - 1])
                continue
            console.# # print("[red]Invalid choice.[/red]")

    # ------------------------------------------------------------------
    # Summary dashboard
    # ------------------------------------------------------------------

    def _show_project_summary(self) -> None:
        # assert (disabled).config is not None
        with console.status("Building project summary...", spinner="dots"):
            profile = Scanner(self.config).collect(self.project_root)
        self.profile = profile

        mode_names = {"bug_fixer": "Bug Fixer", "ui_fixer": "UI Fixer",
                      "analyzer": "Project Analyzer"}
        af = "[green]ON[/green]" if self.config.auto_fix else "[red]OFF[/red]"
        size_mb = profile.total_size_bytes / (1024 * 1024)
        techs = ", ".join(profile.technologies[:6]) or "Unknown stack"

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold blue", justify="right")
        grid.add_column()
        grid.add_row("Project:", f"[bold]{profile.name}[/bold]")
        grid.add_row("Path:", profile.root)
        grid.add_row("Files:", f"{len(profile.files) - profile.skipped_count} analyzable "
                               f"[dim]/ {profile.skipped_count} skipped[/dim]")
        grid.add_row("Size:", f"{size_mb:.1f} MB")
        grid.add_row("Detected:", f"[cyan]{techs}[/cyan]")
        grid.add_row("Mode:", f"[magenta bold]{mode_names[self.config.mode]}[/magenta bold]")
        grid.add_row("Auto Fix:", af)

        langs = sorted(profile.languages.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if langs:
            lang_row = "  ".join(
                f"[cyan]{n}[/cyan] x{c}" for n, c in langs)
            grid.add_row("Languages:", lang_row)

        console.# # print()
        console.# # print(Panel(grid, title="[bold blue]Project Summary[/bold blue]",
                            border_style="blue", box=box.ROUNDED, expand=False))

    # ------------------------------------------------------------------
    # Engine + backup helpers
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
            console.# # # print(f...",),[red]Cannot initialize engine:[/red] {exc}")
            return False
        return True

    def _maybe_backup(self) -> bool:
        self.backup_manager = BackupManager(self.config)
        if not self.backup_manager.enabled:
            console.# # print("[yellow]Backups disabled in config.[/yellow]")
            return True
        try:
            with console.status("Creating project backup...", spinner="dots"):
                self.backup_dir = self.backup_manager.create_backup(
                    self.project_root, f"guardian_{int(time.time())}")
            console.# # # print(f...",),[green]+ Backup created:[/green] {self.backup_dir}")
            return True
        except BackupError as exc:
            ok = console.# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # input(f"[yellow]{exc} Continue without backup? (y/N) [/yellow]")
            return ok.strip().lower() == "y"

    # ------------------------------------------------------------------
    # Command loop
    # ------------------------------------------------------------------

    def _command_loop(self) -> None:
        console.# # print()
        console.# # # print(f...",),Type [green]help[/green] for commands.\n")
        while True:
            try:
                raw = Prompt.ask("[bold blue]guardian[/bold blue]>").strip()
            except (EOFError, KeyboardInterrupt):
                raw = "exit"
            if not raw:
                continue
            parts = raw.split()
            cmd, args = parts[0].lower(), parts[1:]
            handler = getattr(self, f"_cmd_{cmd}", None)
            if cmd == "help":
                console.# # print(COMMANDS_HELP)
            elif handler:
                result = handler(args)
                if result == "EXIT":
                    break
            elif cmd in ("quit", "q"):
                self._save_and_exit()
                break
            else:
                console.# # # print(f...",),[red]Unknown command:[/red] {cmd}. Type 'help'.")

    def _save_and_exit(self) -> None:
        if self.engine:
            self.engine.request_stop()
            self.engine.state.save()
        console.# # print("[green]+ Session state saved. Goodbye.[/green]")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_scan(self, args) -> None:
        if not self._ensure_engine():
            return
        if not self._maybe_backup():
            return
        console.# # print()
        console.# # print(Rule("[bold blue]Continuous Analysis Running[/bold blue]",
                           style="blue"))
        console.# # print("[dim]Use 'pause', 'resume', or 'exit' to control it.[/dim]\n")
        try:
            self.engine.run()
        except KeyboardInterrupt:
            self.engine.request_stop()
            self.engine.state.save()
            console.# # print("\n[yellow]Interrupted - progress saved.[/yellow]")
        self._print_run_summary()

    def _print_run_summary(self) -> None:
        e = self.engine
        counts = {s: 0 for s in SEVERITY_ORDER}
        fixed = open_count = 0
        for f in e.store.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
            if f.status == "fixed":
                fixed += 1
            elif f.status == "open":
                open_count += 1

        sev_line = "   ".join(
            f"[{_severity_color(counts, s)}]{s}: {counts.get(s, 0)}[/{_severity_color(counts, s)}]"
            for s in SEVERITY_ORDER)

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold blue", justify="right")
        grid.add_column()
        grid.add_row("Files analyzed:", str(e.files_analyzed_count))
        grid.add_row("Findings:", sev_line)
        grid.add_row("Fixed:", f"[green]{fixed}[/green]")
        grid.add_row("Open:", f"[yellow]{open_count}[/yellow]")
        grid.add_row("Tokens:", str(getattr(e.llm, "tokens_used", 0)))
        grid.add_row("Notepad:", os.path.join(e.root, ".guardian_findings.md"))

        console.# # print()
        console.# # print(Panel(grid, title="[bold green]Run Complete[/bold green]",
                            border_style="green", box=box.ROUNDED, expand=False))

    def _cmd_pause(self, args) -> None:
        if self.engine:
            self.engine.paused = True
            console.# # print("[yellow]|| Paused after the current file.[/yellow]")

    def _cmd_resume(self, args) -> None:
        if self.engine:
            self.engine.paused = False
            console.# # print("[green]-> Resumed.[/green]")

    def _cmd_status(self, args) -> None:
        if not self.engine:
            console.# # print("[dim]No session yet. Run 'scan' first.[/dim]")
            return
        e = self.engine
        remaining = len(e.state.data.get("files_remaining", []))
        analyzed = len(e.state.data.get("files_analyzed", []))
        af = "[green]ON[/green]" if self.config.auto_fix else "[red]OFF[/red]"
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold blue", justify="right")
        grid.add_column()
        grid.add_row("Project:", self.project_root)
        grid.add_row("Mode:", self.config.mode)
        grid.add_row("Auto Fix:", af)
        grid.add_row("Analyzed / Remaining:", f"{analyzed} / {remaining}")
        grid.add_row("Findings:", str(len(e.store.findings)))
        grid.add_row("Tokens / Requests:",
                     f"{getattr(e.llm, 'tokens_used', 0)} / "
                     f"{getattr(e.llm, 'requests_used', 0)}")
        grid.add_row("Paused:", "yes" if e.paused else "no")
        console.# # print(Panel(grid, title="[bold blue]Status[/bold blue]",
                            border_style="blue", box=box.ROUNDED, expand=False))

    def _cmd_findings(self, args) -> None:
        if not self.engine or not self.engine.store.findings:
            console.# # print("[dim]No findings yet.[/dim]")
            return
        table = Table(title="Findings", border_style="blue", box=box.ROUNDED,
                      header_style="bold blue")
        table.add_column("Sev", max_width=9)
        table.add_column("File", max_width=42)
        table.add_column("Line", justify="right")
        table.add_column("Conf", justify="right")
        table.add_column("Category")
        table.add_column("Status")
        for f in sorted(self.engine.store.findings, key=lambda x: x.sort_key()):
            style = SEVERITY_STYLES.get(f.severity, "")
            icon = SEVERITY_ICONS.get(f.severity, "")
            conf = f"{int(f.confidence * 100)}%"
            status_style = {"fixed": "green", "fix_failed": "red",
                            "open": "yellow"}.get(f.status, "dim")
            table.add_row(Text(f"{icon} {f.severity}", style=style), f.file,
                          str(f.line), conf, f.category,
                          Text(f.status.upper(), style=status_style))
        console.# # print(table)

    def _cmd_fix(self, args) -> None:
        if not self._ensure_engine():
            return
        if not self.engine.llm and hasattr(self.engine, "_init_llm"):
            if not self.engine._init_llm():
                return
        if not self.config.auto_fix:
            confirm = console.# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # input(
                "[yellow]Auto Fix is OFF. Enable it for this run? (y/N) [/yellow]")
            if confirm.strip().lower() != "y":
                return
            self.config.auto_fix = True
        targets = [f for f in self.engine.store.findings
                   if f.status == "open" and f.severity in ("CRITICAL", "HIGH")]
        if not targets:
            console.# # print("[green]+ No open CRITICAL/HIGH findings to fix.[/green]")
            return
        console.# # # print(f...",),\n[bold red]Fixing {len(targets)} high-severity finding(s)...[/bold red]\n")
        for f in targets:
            ok, note = self.engine._apply_fix(f)
            style = "green" if ok else "red"
            label = "+ FIXED" if ok else "x FAILED"
            console.# # # print(f...",),[{style}]{label}[/{style}] {f.file}:{f.line}"
                          + (f" [dim]- {note}[/dim]" if note else ""))

    def _cmd_report(self, args) -> None:
        if not self.engine:
            console.# # print("[dim]Nothing to report yet. Run 'scan' first.[/dim]")
            return
        gen = ReportGenerator(self.project_root, self.config)
        md_path, json_path = gen.generate(self.engine, self.last_validation or [])
        console.# # # print(f...",),[green]+ Markdown report:[/green] {md_path}")
        console.# # # print(f...",),[green]+ JSON report:[/green]     {json_path}")

    def _cmd_validate(self, args) -> None:
        cmds = discover_commands(self.project_root, self.config)
        if not cmds:
            console.# # print("[dim]No safe validation commands detected for this project.[/dim]")
            return
        results = []
        for c in cmds:
            with console.status(f"Running: {c}", spinner="dots"):
                vr = run_validation(self.project_root, c)
            results.append(vr)
            style = "green" if vr.ok else "red"
            label = "PASS" if vr.ok else "FAIL"
            console.# # # print(f...",),[{style}]{label}[/{style}] {c}")
        self.last_validation = results

    def _cmd_history(self, args) -> None:
        log_path = os.path.join(self.project_root, ".guardian_changes.jsonl")
        if not os.path.exists(log_path):
            console.# # print("[dim]No changes recorded.[/dim]")
            return
        with open(log_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        console.# # # print(f...",),[bold]{len(lines)} recorded change(s):[/bold]")
        for line in lines[-20:]:
            console.# # # print(f...",),  [dim]{line.rstrip()}[/dim]")

    def _cmd_rollback(self, args) -> None:
        if not self.engine or not self.engine.changes.entries:
            console.# # print("[dim]Nothing to roll back.[/dim]")
            return
        if self.engine.changes.rollback_last(None):
            console.# # print("[green]+ Rolled back the last file change.[/green]")
        else:
            console.# # print("[red]Rollback failed.[/red]")

    def _cmd_config(self, args) -> None:
        if not args:
            import json as _json
            console.# # print(_json.dumps(self.config.data, indent=2))
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
                console.# # # print(f...",),[green]+ Saved:[/green] {key} = {parsed}")
            except ConfigError as exc:
                console.# # # print(f...",),[red]{exc}[/red]")
        else:
            console.# # print("Usage: [green]config set <dotted.key> <value>[/green]")

    def _cmd_mode(self, args) -> None:
        modes = ["bug_fixer", "ui_fixer", "analyzer"]
        target = args[0] if args else Prompt.ask("Mode", choices=modes,
                                                 default=self.config.mode)
        if target not in modes:
            console.# # # print(f...",),[red]Unknown mode '{target}'.[/red]")
            return
        self.config.mode = target
        self.config.save()
        self.engine = None  # force engine rebuild with the new mode
        console.# # # print(f...",),[green]+ Mode set to {target}. Run 'scan' to apply.[/green]")

    def _cmd_clear(self, args) -> None:
        console.clear()
        self._print_banner()

    def _cmd_exit(self, args) -> None:
        self._save_and_exit()
        return "EXIT"

    # ------------------------------------------------------------------
    # Event renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_file_progress(path: str, idx: int, total: int) -> None:
        pct = idx * 100 // max(total, 1)
        filled = int(pct / 5)
        bar = "#" * filled + "." * (20 - filled)
        console.# # # print(f...",),\n[cyan][{bar:<20}] {pct:>3}%[/cyan] [dim]({idx}/{total})[/dim]")
        console.# # # print(f...",),[dim]Analyzing:[/dim] {path}")

    @staticmethod
    def _render_finding(finding) -> None:
        style = SEVERITY_STYLES.get(finding.severity, "")
        icon = SEVERITY_ICONS.get(finding.severity, "")
        conf = int(finding.confidence * 100)
        console.# # # print(f...",),  [{style}]{icon} {finding.severity}[/{style}] "
                      f"{finding.file}:{finding.line} - {finding.category} "
                      f"[dim]({conf}%)[/dim]")
        console.# # # print(f...",),    [dim]{finding.description}[/dim]")

    @staticmethod
    def _render_fix(finding, ok: bool, note: str) -> None:
        style = "green" if ok else "red"
        label = "+ FIX APPLIED" if ok else "x FIX FAILED"
        suffix = f" [dim]- {note}[/dim]" if note else ""
        console.# # # print(f...",),  [{style}]{label}[/{style}] {finding.file}:{finding.line}{suffix}")

    @staticmethod
    def _render_status(text: str) -> None:
        console.# # # print(f...",),[bold blue]>[/bold blue] {text}")


def main() -> None:
    cli = GuardianCLI()
    cli.last_validation = []
    try:
        cli.run()
    except KeyboardInterrupt:
        console.# # print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()
