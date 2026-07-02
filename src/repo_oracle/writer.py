#!/usr/bin/env python3
"""Repo Oracle — Report Writer.

Saves JSON + HTML reports to the central context repository,
updates per-repo and global index.html files, and optionally
commits and pushes to Forgejo.

Usage:
    python3 writer.py --json report.json --html report.html [--no-git] [--no-push]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Default paths ───────────────────────────────────────────────────────────

DEFAULT_CONTEXT_REPO = os.path.expanduser("~/context-repos/local-project-context")
REPORTS_ROOT = "research/repo-oracle/reports"


# ── File Naming ─────────────────────────────────────────────────────────────

def _report_filename(repo_slug: str, ext: str, suffix: str = "") -> str:
    """Generate a report filename: repo-oracle-<slug>-YYYY-MM-DD[<suffix>].<ext>"""
    today = date.today().isoformat()
    base = f"repo-oracle-{repo_slug}-{today}"
    if suffix:
        base += suffix
    return f"{base}.{ext}"


def _next_collision_suffix(reports_dir: Path, repo_slug: str, ext: str) -> str:
    """Find the next available suffix for same-day reports. Returns '' for no collision."""
    # Check if base name (no suffix) is available
    base = _report_filename(repo_slug, ext)
    if not (reports_dir / base).exists():
        return ""
    # Base taken — try lettered suffixes
    candidates = [chr(ord("a") + i) for i in range(26)]
    for suffix in candidates:
        fname = _report_filename(repo_slug, ext, f"-{suffix}")
        if not (reports_dir / fname).exists():
            return f"-{suffix}"
    # Fallback: timestamp-based
    from time import time
    return f"-{int(time())}"


# ── Index Generation ────────────────────────────────────────────────────────

def _generate_repo_index(repodir: Path, repo_slug: str) -> str:
    """Generate the per-repo index.html listing all reports for a repo slug."""
    reports = []
    if repodir.is_dir():
        files = sorted(repodir.glob("repo-oracle-*.html"), reverse=True)
        for f in files:
            # Parse date from filename
            name = f.stem  # repo-oracle-<slug>-YYYY-MM-DD[-suffix]
            parts = name.split("-")
            date_part = "-".join(parts[-3:]) if len(parts) >= 6 else name
            # Read first few lines for executive summary
            summary = ""
            try:
                content = f.read_text()
                import re
                match = re.search(r'<div class="summary-box">\s*<p>(.*?)</p>', content, re.DOTALL)
                if match:
                    summary = match.group(1).strip()[:200]
            except Exception:
                pass
            file_date = f.stem.replace(f"repo-oracle-{repo_slug}-", "")
            reports.append({
                "filename": f.name,
                "json_filename": f"{f.stem}.json",
                "date": file_date,
                "summary": summary,
            })

    reports_html = ""
    for r in reports:
        reports_html += f"""    <tr>
      <td>{r["date"]}</td>
      <td><a href="./{r['filename']}">HTML Report</a> &middot; <a href="./{r['json_filename']}">JSON</a></td>
      <td>{r['summary'][:150]}</td>
    </tr>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Repo Oracle Reports — {repo_slug}</title>
<link rel="stylesheet" href="/_assets/style.css">
<style>
  :root {{ color-scheme: dark; }}
  body {{ font-family: system-ui, sans-serif; background: #0d1117; color: #c9d1d9; max-width: 800px; margin: 2em auto; padding: 1em; }}
  h1 {{ color: #f0f6fc; border-bottom: 1px solid #21262d; padding-bottom: 0.3em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #30363d; padding: 0.5em; text-align: left; }}
  th {{ background: #161b22; }}
  a {{ color: #58a6ff; }}
  .back {{ margin-bottom: 1em; }}
</style>
</head>
<body>
<div class="back"><a href="../index.html">← All Reports</a></div>
<h1>Repo Oracle Reports: <code>{repo_slug}</code></h1>
<p>All investigation reports for this repository, ordered by date (newest first).</p>
<table>
  <tr><th>Date</th><th>Files</th><th>Summary</th></tr>
{reports_html}</table>
</body>
</html>
"""


def _generate_global_index(reports_root: Path) -> str:
    """Generate the global reports/index.html listing all analyzed repos."""
    repos = []
    if reports_root.is_dir():
        for slug_dir in sorted(reports_root.iterdir()):
            if not slug_dir.is_dir():
                continue
            if slug_dir.name.startswith(".") or slug_dir.name == "index.html":
                continue

            # Count reports and find latest
            html_files = sorted(slug_dir.glob("repo-oracle-*.html"), reverse=True)
            count = len(html_files)
            latest = ""
            latest_summary = ""
            if html_files:
                latest = html_files[0].stem.replace(f"repo-oracle-{slug_dir.name}-", "")
                try:
                    import re
                    content = html_files[0].read_text()
                    match = re.search(r'<div class="summary-box">\s*<p>(.*?)</p>', content, re.DOTALL)
                    if match:
                        latest_summary = match.group(1).strip()[:150]
                except Exception:
                    pass
            repos.append({
                "slug": slug_dir.name,
                "report_count": count,
                "latest_date": latest,
                "latest_summary": latest_summary,
            })

    repos_html = ""
    for r in repos:
        repos_html += f"""    <tr>
      <td><a href="./{r['slug']}/index.html"><code>{r['slug']}</code></a></td>
      <td>{r['report_count']}</td>
      <td>{r['latest_date']}</td>
      <td>{r['latest_summary'][:120]}</td>
    </tr>
"""
    if not repos:
        repos_html = "    <tr><td colspan=\"4\">No reports yet.</td></tr>\n"

    now = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p %Z")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Repo Oracle — All Reports</title>
<link rel="stylesheet" href="/_assets/style.css">
<style>
  :root {{ color-scheme: dark; }}
  body {{ font-family: system-ui, sans-serif; background: #0d1117; color: #c9d1d9; max-width: 900px; margin: 2em auto; padding: 1em; }}
  h1 {{ color: #f0f6fc; border-bottom: 1px solid #21262d; padding-bottom: 0.3em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #30363d; padding: 0.5em; text-align: left; }}
  th {{ background: #161b22; }}
  a {{ color: #58a6ff; }}
  .footer {{ margin-top: 2em; padding-top: 1em; border-top: 1px solid #21262d; font-size: 0.82em; color: #8b949e; }}
</style>
</head>
<body>
<h1>Repo Oracle — All Reports</h1>
<p>Index of all repository investigations. Each repo slug links to its report history.</p>
<table>
  <tr><th>Repository</th><th>Reports</th><th>Latest</th><th>Summary</th></tr>
{repos_html}</table>
<div class="footer">Generated {now}</div>
</body>
</html>
"""


# ── Main Write Function ─────────────────────────────────────────────────────

def write_reports(
    json_path: str,
    html_path: str,
    repo_slug: str,
    context_repo_path: str = DEFAULT_CONTEXT_REPO,
    git_commit: bool = True,
    git_push: bool = True,
) -> dict:
    """Save reports to context repo and optionally commit/push.

    Returns dict with paths and status.
    """
    result: dict = {
        "repo_slug": repo_slug,
        "saved_json": "",
        "saved_html": "",
        "reports_dir": "",
        "global_index": "",
        "repo_index": "",
        "git_committed": False,
        "git_pushed": False,
        "error": None,
    }

    reports_root = Path(context_repo_path, REPORTS_ROOT)
    repodir = reports_root / repo_slug

    try:
        # Create directories
        repodir.mkdir(parents=True, exist_ok=True)
        reports_root.mkdir(parents=True, exist_ok=True)

        # Determine filenames with collision avoidance
        suffix = _next_collision_suffix(repodir, repo_slug, "json")
        json_name = _report_filename(repo_slug, "json", suffix)
        html_name = _report_filename(repo_slug, "html", suffix)

        dest_json = repodir / json_name
        dest_html = repodir / html_name

        # Atomic write: write to temp, then rename
        if not os.path.samefile(os.path.dirname(json_path), str(repodir)):
            shutil.copy2(json_path, str(dest_json))
        else:
            # Source is already in the target dir (e.g., writer.py called with same-dir files)
            pass

        if not os.path.samefile(os.path.dirname(html_path), str(repodir)):
            shutil.copy2(html_path, str(dest_html))

        result["saved_json"] = str(dest_json)
        result["saved_html"] = str(dest_html)
        result["reports_dir"] = str(repodir)

        # Generate indexes
        repo_index_html = _generate_repo_index(repodir, repo_slug)
        repo_index_path = repodir / "index.html"
        repo_index_path.write_text(repo_index_html)
        result["repo_index"] = str(repo_index_path)

        global_index_html = _generate_global_index(reports_root)
        global_index_path = reports_root / "index.html"
        global_index_path.write_text(global_index_html)
        result["global_index"] = str(global_index_path)

        # Git operations
        if git_commit:
            _git_add_commit(context_repo_path, repo_slug, result)
            result["git_committed"] = True

            if git_push:
                _git_push(context_repo_path)
                result["git_pushed"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def _git_add_commit(context_repo_path: str, repo_slug: str, result: dict) -> None:
    """Stage report files and index, commit."""
    rel_root = REPORTS_ROOT
    paths = [
        f"{rel_root}/{repo_slug}/",
        f"{rel_root}/index.html",
    ]
    subprocess.run(
        ["git", "-C", context_repo_path, "add"] + paths,
        capture_output=True, text=True, timeout=10,
        check=True,
    )
    # Check if there's anything staged
    proc = subprocess.run(
        ["git", "-C", context_repo_path, "diff", "--cached", "--quiet"],
        capture_output=True, timeout=10,
    )
    if proc.returncode != 0:
        msg = f"repo-oracle: add report for {repo_slug}"
        subprocess.run(
            ["git", "-C", context_repo_path, "commit", "-m", msg],
            capture_output=True, text=True, timeout=10,
            check=True,
        )


def _git_push(context_repo_path: str) -> None:
    """Push to origin main."""
    subprocess.run(
        ["git", "-C", context_repo_path, "push", "origin", "main"],
        capture_output=True, text=True, timeout=30,
        check=True,
    )


# ── CLI Entry Point ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repo Oracle Writer — save reports to context repository",
    )
    parser.add_argument("--json", required=True, help="Path to JSON report file")
    parser.add_argument("--html", required=True, help="Path to HTML report file")
    parser.add_argument("--slug", required=True, help="Repository slug (sanitized name)")
    parser.add_argument("--context-repo", default=DEFAULT_CONTEXT_REPO,
                        help=f"Path to context repo (default: {DEFAULT_CONTEXT_REPO})")
    parser.add_argument("--no-git", action="store_true", help="Skip git commit")
    parser.add_argument("--no-push", action="store_true", help="Skip git push")
    args = parser.parse_args()

    result = write_reports(
        json_path=args.json,
        html_path=args.html,
        repo_slug=args.slug,
        context_repo_path=args.context_repo,
        git_commit=not args.no_git,
        git_push=not args.no_push,
    )

    if result["error"]:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"Reports saved for '{result['repo_slug']}':")
    print(f"  JSON: {result['saved_json']}")
    print(f"  HTML: {result['saved_html']}")
    print(f"  Index: {result['repo_index']}")
    print(f"  Global Index: {result['global_index']}")
    if result["git_committed"]:
        print(f"  Git: committed")
    if result["git_pushed"]:
        print(f"  Git: pushed to origin")
    print(f"\nHosted URL: http://192.168.50.43:8088/local-project-context/{REPORTS_ROOT}/{args.slug}/")
    print(f"           or https://context.home.arpa/local-project-context/{REPORTS_ROOT}/{args.slug}/")


if __name__ == "__main__":
    main()
