#!/usr/bin/env python3
"""Repo Oracle — JSON Report to HTML Renderer.

Converts a canonical report JSON into a standalone HTML document
using Jinja2 templating. Professional audit styling, dark theme.

Usage:
    python3 render.py --input report.json --output report.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jinja2 import Template

# ── Confidence Badge Helpers ────────────────────────────────────────────────

CONFIDENCE_COLORS: dict[str, str] = {
    "HIGH": "#3fb950",
    "MEDIUM": "#d29922",
    "LOW": "#f85149",
    "UNKNOWN": "#8b949e",
    "N/A": "#484f58",
}

CONFIDENCE_BADGES: dict[str, str] = {
    "HIGH": "🟢 HIGH",
    "MEDIUM": "🟡 MEDIUM",
    "LOW": "🔴 LOW",
    "UNKNOWN": "⬜ UNKNOWN",
    "N/A": "⚫ N/A",
}

PRIORITY_COLORS: dict[str, str] = {
    "URGENT": "#f85149",
    "HIGH": "#f0883e",
    "MEDIUM": "#d29922",
    "LOW": "#3fb950",
    "INFORMATIONAL": "#8b949e",
}

ACTIVITY_COLORS: dict[str, str] = {
    "ACTIVE": "#3fb950",
    "DORMANT": "#d29922",
    "STALE": "#f0883e",
    "ABANDONED": "#f85149",
    "UNKNOWN": "#8b949e",
}


def _confidence_badge(confidence: str) -> str:
    return CONFIDENCE_BADGES.get(confidence, f"⬜ {confidence}")


def _priority_badge(priority: str) -> str:
    color = PRIORITY_COLORS.get(priority, "#8b949e")
    return f'<span class="badge" style="background:{color}20;color:{color};border:1px solid {color};">{priority}</span>'


def _activity_badge(activity: str) -> str:
    color = ACTIVITY_COLORS.get(activity, "#8b949e")
    return f'<span class="badge" style="background:{color}20;color:{color};border:1px solid {color};">{activity}</span>'


# ── HTML Template ───────────────────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_HTML_TEMPLATE_PATH = _TEMPLATE_DIR / "report.html.j2"


def _load_template() -> Template:
    """Load the Jinja2 template from file, with inline fallback."""
    if _HTML_TEMPLATE_PATH.is_file():
        return Template(_HTML_TEMPLATE_PATH.read_text())
    return Template(
        "<html><body><h1>{{ report.metadata.repo_name }}</h1><p>Report template not found.</p></body></html>"
    )


_MD_TEMPLATE_PATH = _TEMPLATE_DIR / "report.md.j2"


def _load_md_template() -> Template:
    if _MD_TEMPLATE_PATH.is_file():
        return Template(_MD_TEMPLATE_PATH.read_text())
    return Template("# {{ report.metadata.repo_name }}\n\nReport template not found.")


def render_markdown(report: dict) -> str:
    """Render a Report dict to Markdown string."""
    template = _load_md_template()
    template.globals["confidence_badge"] = _confidence_badge
    return template.render(report=report)


# ── Jinja2 Filter Helpers ───────────────────────────────────────────────────


def _confidence_color(confidence: str) -> str:
    return CONFIDENCE_COLORS.get(confidence, "#8b949e")


def _evidence_link(eid: str) -> str:
    return f'<code class="evidence-ref">{eid}</code>'


# ── Render Function ─────────────────────────────────────────────────────────


def render_report(report: dict, json_filename: str = "") -> str:
    """Render a Report dict to standalone HTML string."""
    template = _load_template()

    # Register global functions
    template.globals["confidence_badge"] = _confidence_badge
    template.globals["confidence_color"] = _confidence_color
    template.globals["priority_badge"] = _priority_badge
    template.globals["activity_badge"] = _activity_badge

    # Register filters (used with pipe syntax)
    template.environment.filters["evidence_link"] = _evidence_link

    html = template.render(
        report=report,
        report_filename_json=json_filename or "report.json",
    )
    return html


# ── CLI Entry Point ─────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repo Oracle Renderer — convert JSON report to HTML",
    )
    parser.add_argument("--input", "-i", required=True, help="Input JSON report file")
    parser.add_argument("--output", "-o", required=True, help="Output HTML file path")
    args = parser.parse_args()

    # Load report
    with open(args.input) as f:
        report = json.load(f)

    # Determine JSON filename for footer link
    json_filename = Path(args.input).name

    # Render
    html = render_report(report, json_filename)

    # Write
    with open(args.output, "w") as f:
        f.write(html)

    print(f"HTML report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
