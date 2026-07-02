"""CLI entry point — Typer + Rich.

Commands:
    repo-oracle [PATH]          Investigate a repo (default: cwd)
    repo-oracle scan [PATH]     Deterministic scan only (QUICK tier)
    repo-oracle version         Show version
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from repo_oracle import scan_repo, render_report, __version__
from repo_oracle.schema import (
    empty_report,
    new_finding,
    new_recommendation,
    new_evidence,
    validate_report_strict,
    ALL_DIMENSIONS,
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
        capture_output=True,
        text=True,
        timeout=60,
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
    for i, dim in enumerate(ALL_DIMENSIONS):
        report["dimensions"][i] = new_finding(
            dim,
            "MEDIUM",
            f"Scanned: {scan['total_files']} files in {len(scan['languages'])} languages",
            ["scan:files"],
        )
    return report


def _build_oss_report(scan: dict) -> dict:
    """Build an OSS-focused report: contribution readiness or library utilization."""
    report = empty_report(scan["repo_path"], scan["repo_name"], scan["repo_slug"])
    report["scanner_output"] = scan

    # Assess OSS signals from scanner output
    top_langs = list(scan["languages"].keys())[:3]
    has_contrib = any("CONTRIBUTING" in f.upper() for f in scan["documentation_files"])
    has_license = any("LICENSE" in f.upper() for f in scan["documentation_files"])
    has_ci = len(scan["ci_cd_files"]) > 0
    has_tests = len(scan["test_frameworks"]) > 0
    issues_link = (
        f"https://github.com/{scan['git_remote'].split('github.com/')[-1].replace('.git', '')}/issues"
        if "github.com" in (scan.get("git_remote") or "")
        else ""
    )

    # Executive summary
    activity_label = (
        "Active" if scan["has_git"] and scan["commit_count"] > 10 else "Dormant"
    )
    report["executive_summary"] = (
        f"{scan['repo_name']} is a{'n' if top_langs[0][0].lower() in 'aeiou' else ''} "
        f"{top_langs[0] if top_langs else 'unknown'}-based project with "
        f"{scan['total_files']} files and {scan['commit_count']} commits. "
        f"OSS readiness: {'Good — has CONTRIBUTING guide, CI, and tests' if has_contrib and has_ci and has_tests else 'Partial — missing some OSS infrastructure'}. "
        f"This report focuses on {'contribution readiness and library utilization' if 'library' in scan['repo_name'].lower() or 'sdk' in scan['repo_name'].lower() or 'lib' in scan['repo_name'].lower() else 'open-source contribution assessment'}."
    )

    # Purpose
    report["purpose"] = new_finding(
        "purpose",
        "HIGH",
        f"{scan['repo_name']}: {', '.join(top_langs)} project. "
        f"{'Well-structured for external contributors.' if has_contrib else 'Needs contribution documentation.'}",
        ["scan:readme", "scan:languages"]
        + (
            [f"file:{f}" for f in scan["documentation_files"][:2]]
            if scan["documentation_files"]
            else []
        ),
        "OSS reframing: evaluating suitability for external contribution or library adoption.",
    )

    report["vital_signs"] = {
        "activity": activity_label.upper(),
        "language": ", ".join(top_langs) if top_langs else "Unknown",
        "build_system": ", ".join(scan["build_systems"])
        if scan["build_systems"]
        else "None detected",
    }

    # OSS-specific dimensions
    oss_dims = {
        "purpose": (
            "HIGH",
            f"OSS project: {', '.join(top_langs)}. {'Active community' if scan['commit_count'] > 50 else 'Small/early project'}.",
            "scan:languages",
            f"{scan['total_files']} files, {scan['commit_count']} commits",
        ),
        "languages_and_frameworks": (
            "HIGH",
            f"Primary: {', '.join(top_langs)}. {len(scan['languages'])} languages total.",
            "scan:languages",
            "Check language familiarity before contributing.",
        ),
        "build_and_test_system": (
            "HIGH" if has_ci else "MEDIUM",
            f"{'CI/CD configured' if has_ci else 'No CI detected'}. {'Tests: ' + ', '.join(scan['test_frameworks']) if has_tests else 'No test framework detected'}.",
            "scan:build",
            "Build system determines local dev setup complexity.",
        ),
        "entrypoints": (
            "MEDIUM",
            f"Entrypoints: {', '.join(scan['entrypoints'][:5]) if scan['entrypoints'] else 'Unclear'}.",
            "scan:entrypoints",
            "Entrypoints guide first-time explorers to the right starting point.",
        ),
        "architecture": (
            "MEDIUM",
            f"Structure: {', '.join(scan['top_level_dirs']) if scan['top_level_dirs'] else 'Flat'}.",
            "scan:top_level_dirs",
            "Clear architecture helps contributors find their way.",
        ),
        "dependency_graph": (
            "MEDIUM",
            f"Dependency files: {', '.join(scan['dependency_files']) if scan['dependency_files'] else 'None detected'}.",
            "scan:dependency_files",
            "Understand what the project depends on before integrating.",
        ),
        "runtime_assumptions": (
            "MEDIUM",
            f"Platform: Python {'3.11+' if any('.py' in f for f in scan.get('all_files', [])) else 'unknown'}.",
            "scan:languages",
            "Verify your environment matches before contributing.",
        ),
        "stale_dependencies": (
            "MEDIUM",
            "Check dependency freshness before integrating. Run pip-audit or npm audit.",
            "scan:dependency_files",
            "Stale dependencies increase security risk for downstream consumers.",
        ),
        "git_history": (
            "HIGH" if scan["has_git"] else "LOW",
            f"{scan['commit_count']} commits, last: {scan['last_commit_date'][:10]}. {'Active development.' if scan['commit_count'] > 20 else 'Early stage.'}",
            "scan:git",
            "Frequent commits signal active maintenance.",
        ),
        "open_todos": (
            "LOW",
            "Scan for TODO/FIXME markers to find easy first-contribution opportunities.",
            "",
            "TODOs often make great starter issues for new contributors.",
        ),
        "documentation_quality": (
            "HIGH" if has_contrib else "MEDIUM",
            f"{'CONTRIBUTING guide found' if has_contrib else 'No CONTRIBUTING guide'}. {'LICENSE: ' + [f for f in scan['documentation_files'] if 'LICENSE' in f.upper()][0] if has_license else 'No LICENSE file — project may not be open-source.'}.",
            "scan:documentation_files",
            "Documentation quality directly impacts contribution velocity.",
        ),
        "test_coverage": (
            "HIGH" if has_tests else "LOW",
            f"{'Tests present: ' + ', '.join(scan['test_frameworks']) if has_tests else 'No tests detected — risky to contribute without tests.'}.",
            "scan:tests",
            "Good test coverage protects your contributions from regression.",
        ),
        "security_surface": (
            "MEDIUM",
            f"{'Secret files detected: ' + str(len(scan['secret_files_detected'])) if scan['secret_files_detected'] else 'No secret files detected.'}.",
            "scan:secrets",
            "Before contributing, ensure you understand the security posture.",
        ),
        "deployment_clues": (
            "LOW",
            f"{'CI/CD: ' + ', '.join(scan['ci_cd_files'][:3]) if has_ci else 'No CI/CD'}. Docker: {'Yes' if scan['docker_files'] else 'No'}.",
            "scan:docker",
            "CI/CD status tells you if contributions will pass checks.",
        ),
        "activity_signal": (
            "HIGH",
            f"{'ACTIVE — frequent commits, CI active' if scan['commit_count'] > 20 and has_ci else 'DORMANT — slow development, may accept contributions slowly'}.",
            "scan:git",
            "",
        ),
        "value_assessment": (
            "HIGH",
            f"{'Good candidate for contribution' if has_contrib and has_ci and has_tests else 'Needs OSS infrastructure before contributing'}. {'Has license' if has_license else '⚠ No license — project may not be open-source!'}.",
            "scan:documentation_files",
            "",
        ),
        "next_action_recommendation": (
            "HIGH",
            _oss_next_action(has_contrib, has_ci, has_tests, has_license, scan),
            "scan:documentation_files",
            "",
        ),
    }

    for i, dim in enumerate(ALL_DIMENSIONS):
        conf, summary, evidence, details = oss_dims[dim]
        report["dimensions"][i] = new_finding(
            dim, conf, summary, [evidence] if evidence else [], details
        )

    # OSS recommendations
    recs = []
    if not has_license:
        recs.append(
            new_recommendation(
                "oss-1",
                "DOCUMENT",
                "URGENT",
                "Add a LICENSE file before contributing or using this project",
                "No LICENSE file detected. Without an open-source license, the project is proprietary by default. You cannot legally use or contribute to it.",
                ["scan:documentation_files"],
                "TRIVIAL",
                "Legal risk. Without a license, your contributions or usage could violate copyright.",
            )
        )
    if not has_contrib:
        recs.append(
            new_recommendation(
                "oss-2",
                "DOCUMENT",
                "HIGH",
                "Add a CONTRIBUTING.md guide",
                "No contribution guide found. New contributors don't know how to set up, test, or submit changes.",
                ["scan:documentation_files"],
                "SMALL",
                "Fewer external contributors. People who want to help can't figure out how.",
            )
        )
    if not has_tests:
        recs.append(
            new_recommendation(
                "oss-3",
                "TEST-FIRST-REPAIR",
                "HIGH",
                "Add tests before contributing significant changes",
                "No test framework detected. Contributing to untested code is risky — you might break things without knowing.",
                ["scan:tests"],
                "MEDIUM",
                "Your contributions could introduce regressions with no safety net.",
            )
        )
    if not has_ci:
        recs.append(
            new_recommendation(
                "oss-4",
                "PRODUCTIZE",
                "MEDIUM",
                "Set up CI/CD (GitHub Actions recommended)",
                "No CI detected. Without automated checks, contributions may introduce lint, type, or test failures unnoticed.",
                ["scan:ci_cd"],
                "SMALL",
                "Manual review bottleneck. CI catches issues before maintainers spend time reviewing.",
            )
        )
    recs.append(
        new_recommendation(
            "oss-5",
            "DOCUMENT",
            "MEDIUM",
            "Look for 'good first issue' labels to start contributing",
            f"{'Check: ' + issues_link if issues_link else 'Search the issue tracker'} for beginner-friendly issues.",
            ["scan:git"],
            "TRIVIAL",
            "Jumping into a complex codebase without guidance leads to frustration.",
        )
    )
    recs.append(
        new_recommendation(
            "oss-6",
            "DEPENDENCY-UPDATE",
            "LOW",
            "Audit dependencies for security before integrating into your project",
            "Run pip-audit / npm audit on the dependency tree. Check for known CVEs.",
            ["scan:dependency_files"],
            "SMALL",
            "Integrating insecure dependencies exposes your project to supply-chain attacks.",
        )
    )

    report["recommendations"] = recs

    # Next actions
    actions = []
    if has_contrib and has_tests:
        actions.append("1. Clone and run tests locally: git clone + pytest/tox")
        actions.append("2. Find a 'good first issue' in the issue tracker")
        actions.append("3. Fork, branch, implement, test, PR")
    else:
        actions.append("1. Ask maintainers about contribution process (open an issue)")
        actions.append("2. Help add CONTRIBUTING.md if it's missing")
        actions.append(
            "3. Add tests for the area you want to change before refactoring"
        )
    actions.append(
        f"4. {'Integrate via pip install' if 'library' in scan['repo_name'].lower() or 'sdk' in scan['repo_name'].lower() else 'Use as a dependency in your project'}"
    )
    report["next_actions"] = actions

    # Evidence registry
    for eid in [
        "scan:languages",
        "scan:build",
        "scan:tests",
        "scan:git",
        "scan:docs",
        "scan:entrypoints",
        "scan:top_level_dirs",
        "scan:dependency_files",
        "scan:documentation_files",
        "scan:ci_cd",
        "scan:docker",
        "scan:secrets",
        "scan:files",
        "scan:readme",
    ]:
        if eid == "scan:readme":
            report["evidence_registry"][eid] = new_evidence(
                eid,
                "scan",
                "README analyzed for project purpose and setup instructions",
            )
        elif eid == "scan:docs":
            report["evidence_registry"][eid] = new_evidence(
                eid,
                "scan",
                f"Documentation files: {scan.get('documentation_files', [])}",
            )

    report["security_notes"] = [
        f"{len(scan['secret_files_detected'])} secret files detected (contents not inspected)."
        if scan["secret_files_detected"]
        else "No secret files detected.",
        "Always run pip-audit / npm audit before integrating dependencies.",
        "Check the license before using this code in a commercial product.",
    ]

    return report


def _oss_next_action(
    has_contrib: bool, has_ci: bool, has_tests: bool, has_license: bool, scan: dict
) -> str:
    if not has_license:
        return "⚠ BLOCKED: No license. Cannot legally use or contribute. Ask maintainers to add one."
    if has_contrib and has_ci and has_tests:
        return (
            "Ready for contribution. Clone, find a good first issue, and submit a PR."
        )
    missing = []
    if not has_contrib:
        missing.append("CONTRIBUTING.md")
    if not has_tests:
        missing.append("tests")
    if not has_ci:
        missing.append("CI/CD")
    return f"Needs OSS infra: {', '.join(missing)}. Help add these before contributing."


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

    lang_str = ", ".join(
        f"{lang} ({n})" for lang, n in list(scan["languages"].items())[:5]
    )
    table.add_row("Languages", lang_str)
    table.add_row("Build", ", ".join(scan["build_systems"]) or "None detected")
    table.add_row("Tests", ", ".join(scan["test_frameworks"]) or "None detected")
    table.add_row("Files", f"{scan['total_files']} files, {scan['total_dirs']} dirs")
    if scan["has_git"]:
        table.add_row("Git", f"Last commit: {scan['last_commit_date'][:10]}")
        table.add_row("Remote", scan["git_remote"] or "None")
    if scan["dirty"]:
        table.add_row(
            "Status",
            f"[yellow]Dirty[/yellow] ({scan['modified_count']} mod, {scan['untracked_count']} untracked)",
        )
    table.add_row(
        "GitNexus",
        f"{scan['gitnexus_symbols']} symbols"
        if scan["has_gitnexus"]
        else "Not indexed",
    )
    if scan["secret_files_detected"]:
        table.add_row(
            "Secrets",
            f"[red]{len(scan['secret_files_detected'])} files detected (not read)[/red]",
        )

    console.print(table)


def _render_rich_recommendations(report: dict) -> None:
    """Print top 3 recommendations."""
    recs = report.get("recommendations", [])
    if not recs:
        return
    console.print("\n[bold]Top Recommendations:[/bold]")
    for rec in recs[:3]:
        prio_style = {
            "URGENT": "bold red",
            "HIGH": "red",
            "MEDIUM": "yellow",
            "LOW": "green",
            "INFORMATIONAL": "dim",
        }.get(rec["priority"], "dim")
        console.print(
            f"  [{prio_style}]{rec['priority']}[/{prio_style}] {rec['action']}"
        )


# ── Commands ────────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Show version and exit."""
    console.print(f"[bold]repo-oracle[/bold] [green]{__version__}[/green]")
    console.print("Investigate any Git repository with one command.", style="dim")


@app.command()
def scan(
    path: str = typer.Argument(".", help="Path to repository (local dir or Git URL)"),
    json_output: bool = typer.Option(
        False, "--json", help="Output scanner JSON to stdout"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Run deterministic scanner only (QUICK tier)."""
    target = path
    tmpdir: Optional[str] = None

    if target.startswith("http://") or target.startswith("https://"):
        tmpdir = _clone_url(target)
        target = tmpdir

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=err_console,
        ) as progress:
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
    output_dir: str = typer.Option(
        "./repo-oracle-reports",
        "--output-dir",
        "-o",
        help="Directory for report output",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output report JSON to stdout"
    ),
    html: bool = typer.Option(True, "--html/--no-html", help="Generate HTML report"),
    markdown: bool = typer.Option(
        False, "--markdown", "-m", help="Generate Markdown report"
    ),
    open_browser: bool = typer.Option(
        False, "--open", help="Open HTML report in browser"
    ),
    tier: str = typer.Option(
        "deep", "--tier", "-t", help="Analysis tier: quick | deep"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    oss: bool = typer.Option(
        False, "--oss", help="Reframe for open-source contribution or utilization"
    ),
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
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=err_console,
            ) as progress:
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
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=err_console,
            ) as progress:
                progress.add_task("Building report...", total=None)
                if tier == "deep":
                    report = (
                        _build_oss_report(scan_result)
                        if oss
                        else _build_quick_report(scan_result)
                    )
                else:
                    report = _build_quick_report(scan_result)
        else:
            report = (
                _build_oss_report(scan_result)
                if oss
                else _build_quick_report(scan_result)
            )

        duration = time.time() - start_time
        report["metadata"]["analysis_duration_seconds"] = round(duration, 1)
        report["metadata"]["analysis_tier"] = (
            tier.upper() if tier == "deep" else "QUICK"
        )
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

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        if html:
            html_content = render_report(report, os.path.basename(json_path))
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        md_path = None
        if markdown:
            from repo_oracle.render import render_markdown

            md_path = os.path.join(output_dir, f"repo-oracle-{slug}-{today}.md")
            with open(md_path, "w", encoding="utf-8") as f:
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
