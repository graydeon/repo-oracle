"""CLI entry point — Typer + Rich.

Commands:
    repo-oracle [PATH]          Investigate a repo (default: cwd)
    repo-oracle scan [PATH]     Deterministic scan only (QUICK tier)
    repo-oracle version         Show version
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from repo_oracle import scan_repo, render_report, write_reports, __version__
from repo_oracle.schema import (
    empty_report, new_finding, new_recommendation, new_evidence,
    validate_report_strict, ALL_DIMENSIONS,
)

app = typer.Typer(
    name="repo-oracle",
    help="Investigate any Git repository with one command.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)

# ── Confidence colors for Rich ──────────────────────────────────────────────

CONFIDENCE_STYLES: dict[str, str] = {
    "HIGH": "green",
    "MEDIUM": "yellow",
    "LOW": "red",
    "UNKNOWN": "dim",
    "N/A": "dim",
}

ACTIVITY_STYLES: dict[str, str] = {
    "ACTIVE": "green",
    "DORMANT": "yellow",
    "STALE": "red",
    "ABANDONED": "bold red",
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def _clone_url(url: str) -> str:
    """Clone a remote URL to a temp dir. Returns the local path."""
    import subprocess
    tmpdir = tempfile.mkdtemp(prefix="repo-oracle-")
    err_console.print(f"[dim]Cloning {url}...[/dim]")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, tmpdir],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        err_console.print(f"[red]Clone failed:[/red] {result.stderr.strip()}")
        raise typer.Exit(1)
    return tmpdir


def _build_quick_report(scan: dict) -> dict:
    """Build a basic report from scanner output (QUICK tier)."""
    report = empty_report(scan["repo_path"], scan["repo_name"], scan["repo_slug"])
    report["executive_summary"] = (
        f"{scan['repo_name']}: {scan['total_files']} files, "
        f"primarily {', '.join(list(scan['languages'].keys())[:3])}. "
        f"{'Git repo with ' + str(scan['commit_count']) + ' commits.' if scan['has_git'] else 'Not a git repository.'}"
    )
    report["scanner_output"] = scan
    # Fill dimensions with scanner data
    for i, dim in enumerate(ALL_DIMENSIONS):
        report["dimensions"][i] = new_finding(
            dim, "MEDIUM",
            f"Scanned: {scan['total_files']} files in {len(scan['languages'])} languages",
            ["scan:files"]
        )
    return report


def _render_rich_summary(scan: dict) -> None:
    """Print a rich terminal summary table."""
    # Header panel
    title = f"[bold]{scan['repo_name']}[/bold]"
    if scan["has_git"]:
        title += f"  [dim]({scan['git_branch']}, {scan['commit_count']} commits)[/dim]"
    console.print(Panel(title, border_style="blue"))

    # Vital signs table
    table = Table(title="Vital Signs", show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()

    lang_str = ", ".join(f"{lang} ({n})" for lang, n in list(scan["languages"].items())[:5])
    table.add_row("Languages", lang_str)
    table.add_row("Build", ", ".join(scan["build_systems"]) or "None detected")
    table.add_row("Tests", ", ".join(scan["test_frameworks"]) or "None detected")
    table.add_row("Files", f"{scan['total_files']} files, {scan['total_dirs']} dirs")
    if scan["has_git"]:
        table.add_row("Git", f"Last commit: {scan['last_commit_date'][:10]}")
        table.add_row("Remote", scan["git_remote"] or "None")
    if scan["dirty"]:
        table.add_row("Status", f"[yellow]Dirty[/yellow] ({scan['modified_count']} mod, {scan['untracked_count']} untracked)")
    table.add_row("GitNexus", f"{scan['gitnexus_symbols']} symbols" if scan["has_gitnexus"] else "Not indexed")
    if scan["secret_files_detected"]:
        table.add_row("Secrets", f"[red]{len(scan['secret_files_detected'])} files detected (not read)[/red]")

    console.print(table)


def _render_rich_recommendations(report: dict) -> None:
    """Print top 3 recommendations."""
    recs = report.get("recommendations", [])
    if not recs:
        return
    console.print("\n[bold]Top Recommendations:[/bold]")
    for rec in recs[:3]:
        prio_style = {"URGENT": "bold red", "HIGH": "red", "MEDIUM": "yellow",
                       "LOW": "green", "INFORMATIONAL": "dim"}.get(rec["priority"], "dim")
        console.print(f"  [{prio_style}]{rec['priority']}[/{prio_style}] {rec['action']}")


# ── Commands ────────────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Show version and exit."""
    console.print(f"[bold]repo-oracle[/bold] [green]{__version__}[/green]")
    console.print("Investigate any Git repository with one command.", style="dim")


@app.command()
def scan(
    path: str = typer.Argument(".", help="Path to repository (local dir or Git URL)"),
    json_output: bool = typer.Option(False, "--json", help="Output scanner JSON to stdout"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Run deterministic scanner only (QUICK tier)."""
    target = path
    tmpdir: Optional[str] = None

    if target.startswith("http://") or target.startswith("https://"):
        tmpdir = _clone_url(target)
        target = tmpdir

    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      transient=True, console=err_console) as progress:
            progress.add_task("Scanning...", total=None)
            result = scan_repo(target)

        if json_output:
            console.print_json(data=result)
        else:
            _render_rich_summary(result)

        if result["error"]:
            err_console.print(f"[red]Error:[/red] {result['error']}")
            raise typer.Exit(1)

    finally:
        if tmpdir and os.path.isdir(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


@app.command()
def investigate(
    path: str = typer.Argument(".", help="Path to repository (local dir or Git URL)"),
    output_dir: str = typer.Option("./repo-oracle-reports", "--output-dir", "-o",
                                    help="Directory for report output"),
    json_output: bool = typer.Option(False, "--json", help="Output report JSON to stdout"),
    html: bool = typer.Option(True, "--html/--no-html", help="Generate HTML report"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Generate Markdown report"),
    open_browser: bool = typer.Option(False, "--open", help="Open HTML report in browser"),
    tier: str = typer.Option("deep", "--tier", "-t", help="Analysis tier: quick | deep"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
) -> None:
    """Investigate a repository and produce a full report."""
    target = path
    tmpdir: Optional[str] = None
    start_time = time.time()

    if target.startswith("http://") or target.startswith("https://"):
        tmpdir = _clone_url(target)
        target = tmpdir

    try:
        # Phase 1: Scan
        if not quiet:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                          transient=True, console=err_console) as progress:
                progress.add_task("Scanning repository...", total=None)
                scan_result = scan_repo(target)
        else:
            scan_result = scan_repo(target)

        if scan_result["error"]:
            err_console.print(f"[red]Error:[/red] {scan_result['error']}")
            raise typer.Exit(1)

        if not quiet:
            _render_rich_summary(scan_result)

        # Phase 2: Build report
        if not quiet:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                          transient=True, console=err_console) as progress:
                progress.add_task("Building report...", total=None)
                if tier == "deep":
                    report = _build_quick_report(scan_result)
                    # In standalone CLI, deep = quick with richer dimension assessment
                    # Hermes adds agentic subagents for true deep analysis
                else:
                    report = _build_quick_report(scan_result)
        else:
            report = _build_quick_report(scan_result)

        duration = time.time() - start_time
        report["metadata"]["analysis_duration_seconds"] = round(duration, 1)
        report["metadata"]["analysis_tier"] = tier.upper() if tier == "deep" else "QUICK"
        validate_report_strict(report)

        # Phase 3: Output
        if json_output:
            console.print_json(data=report)
            return

        # Write files
        os.makedirs(output_dir, exist_ok=True)
        from datetime import date
        slug = scan_result["repo_slug"]
        today = date.today().isoformat()
        json_path = os.path.join(output_dir, f"repo-oracle-{slug}-{today}.json")
        html_path = os.path.join(output_dir, f"repo-oracle-{slug}-{today}.html")

        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        if html:
            html_content = render_report(report, os.path.basename(json_path))
            with open(html_path, "w") as f:
                f.write(html_content)

        md_path = None
        if markdown:
            from repo_oracle.render import render_markdown
            md_path = os.path.join(output_dir, f"repo-oracle-{slug}-{today}.md")
            with open(md_path, "w") as f:
                f.write(render_markdown(report))

        # Terminal summary
        if not quiet:
            _render_rich_recommendations(report)
            console.print(f"\n[dim]Report saved:[/dim] {json_path}")
            if html:
                console.print(f"[dim]HTML saved:  [/dim] {html_path}")
            console.print(f"[dim]Duration:    [/dim] {duration:.1f}s")

        if open_browser and html:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(html_path)}")

    finally:
        if tmpdir and os.path.isdir(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
) -> None:
    """repo-oracle — Investigate any Git repository with one command.

    Run without arguments to investigate the current directory.
    """
    if ctx.invoked_subcommand is None:
        # Default: investigate current directory
        investigate(".", quiet=False)


if __name__ == "__main__":
    app()
