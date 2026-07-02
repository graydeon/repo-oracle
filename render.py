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
from datetime import datetime
from pathlib import Path
from typing import Any

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

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="generator" content="Repo Oracle">
<meta name="repo" content="{{ report.metadata.repo_name }}">
<meta name="analysis-date" content="{{ report.metadata.analysis_timestamp }}">
<title>Repo Oracle Report — {{ report.metadata.repo_name }}</title>
<link rel="stylesheet" href="/_assets/style.css">
<style>
  :root { color-scheme: dark; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; max-width: 960px; margin: 2em auto; padding: 1em; line-height: 1.6; }
  h1,h2,h3,h4 { color: #f0f6fc; border-bottom: 1px solid #21262d; padding-bottom: 0.3em; }
  h1 { font-size: 1.5em; } h2 { font-size: 1.25em; } h3 { font-size: 1.1em; }
  a { color: #58a6ff; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th, td { border: 1px solid #30363d; padding: 0.5em 0.7em; text-align: left; }
  th { background: #161b22; font-weight: 600; }
  td { font-size: 0.92em; }
  pre { background: #161b22; border-radius: 6px; padding: 1em; overflow-x: auto; line-height: 1.4; font-size: 0.88em; }
  code { background: #161b22; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
  .header-bar { background: #161b22; padding: 1.5em; border-radius: 8px; margin-bottom: 2em; border: 1px solid #30363d; }
  .header-bar h1 { margin-top: 0; border: none; }
  .meta-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.5em 1.5em; }
  .meta-item { font-size: 0.88em; color: #8b949e; }
  .meta-item strong { color: #c9d1d9; }
  .badge { display: inline-block; padding: 0.15em 0.6em; border-radius: 4px; font-size: 0.82em; font-weight: 600; margin: 0 0.2em; }
  .conf-HIGH { color: #3fb950; } .conf-MEDIUM { color: #d29922; } .conf-LOW { color: #f85149; }
  .conf-UNKNOWN { color: #8b949e; } .conf-NA { color: #484f58; }
  .toc { margin: 1.5em 0; padding: 1em 1.5em; background: #161b22; border-radius: 6px; }
  .toc ol { margin: 0.5em 0; } .toc li { margin: 0.3em 0; }
  .finding { margin: 0.8em 0; padding: 0.6em 1em; background: #161b22; border-radius: 6px; border-left: 3px solid #30363d; }
  .finding.evidence { border-left-color: #3fb950; }
  .finding.assumption { border-left-color: #d29922; }
  .rec-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1em 1.2em; margin: 1em 0; }
  .rec-card .rec-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5em; }
  .rec-card .rec-title { font-weight: 600; color: #f0f6fc; }
  .security-note { background: #3a1a1a; border: 1px solid #f85149; border-radius: 6px; padding: 0.6em 1em; margin: 0.5em 0; font-size: 0.9em; }
  .unknown-box { background: #1a1a2a; border: 1px solid #8b949e; border-radius: 6px; padding: 0.6em 1em; margin: 0.5em 0; }
  .evidence-ref { font-family: monospace; font-size: 0.85em; color: #58a6ff; }
  .footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid #21262d; font-size: 0.82em; color: #8b949e; }
  .section { margin: 2em 0; }
  .assumption-tag { color: #d29922; font-style: italic; }
  .rec-evidence { font-size: 0.85em; color: #8b949e; margin-top: 0.5em; }
  .rec-risks { font-size: 0.9em; color: #f85149; margin-top: 0.3em; }
  .next-action { padding: 0.4em 0.8em; margin: 0.3em 0; background: #1a3a1a; border-radius: 4px; border-left: 3px solid #3fb950; }
  .summary-box { background: #161b22; border-radius: 8px; padding: 1.2em 1.5em; margin: 1em 0; border: 1px solid #30363d; }
  .summary-box p { font-size: 1.05em; margin: 0; }
  @media (max-width: 600px) {
    body { margin: 0.5em; padding: 0.5em; }
    .meta-grid { grid-template-columns: 1fr; }
    .rec-card .rec-header { flex-direction: column; align-items: flex-start; }
  }
</style>
</head>
<body>

<div class="header-bar">
  <h1>Repo Oracle Report</h1>
  <div class="meta-grid">
    <div class="meta-item"><strong>Repository:</strong> {{ report.metadata.repo_name }}</div>
    <div class="meta-item"><strong>Path:</strong> <code>{{ report.metadata.repo_path }}</code></div>
    <div class="meta-item"><strong>Analysis Tier:</strong> {{ report.metadata.analysis_tier }}</div>
    <div class="meta-item"><strong>Date:</strong> {{ report.metadata.analysis_timestamp[:19] }}</div>
    <div class="meta-item"><strong>Tool Calls:</strong> {{ report.metadata.total_tool_calls }}</div>
    <div class="meta-item"><strong>Duration:</strong> {{ "%.1f"|format(report.metadata.analysis_duration_seconds) }}s</div>
    <div class="meta-item"><strong>GitNexus:</strong> {{ "Yes" if report.metadata.gitnexus_used else "No" }}</div>
    <div class="meta-item"><strong>Hermes:</strong> {{ report.metadata.hermes_version }}</div>
  </div>
</div>

<div class="toc">
<strong>Table of Contents</strong>
<ol>
  <li><a href="#summary">Executive Summary</a></li>
  <li><a href="#vitals">Vital Signs</a></li>
  <li><a href="#purpose">Purpose</a></li>
  <li><a href="#dimensions">Analysis Dimensions</a></li>
  <li><a href="#security">Security Notes</a></li>
  <li><a href="#contradictions">Contradictions &amp; Unknowns</a></li>
  <li><a href="#recommendations">Recommendations</a></li>
  <li><a href="#next-actions">Next Actions</a></li>
  <li><a href="#evidence">Evidence Registry</a></li>
  <li><a href="#appendix">Appendix</a></li>
</ol>
</div>

<!-- ===== EXECUTIVE SUMMARY ===== -->
<div class="section" id="summary">
<h2>1. Executive Summary</h2>
<div class="summary-box">
  <p>{{ report.executive_summary }}</p>
</div>
</div>

<!-- ===== VITAL SIGNS ===== -->
<div class="section" id="vitals">
<h2>2. Vital Signs</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Activity Status</td><td>{{ activity_badge(report.vital_signs.activity) }}</td></tr>
  <tr><td>Primary Language</td><td>{{ report.vital_signs.language }}</td></tr>
  <tr><td>Build System</td><td>{{ report.vital_signs.build_system }}</td></tr>
  <tr><td>Git</td><td>{{ "Yes" if report.scanner_output.has_git else "No" }}{% if report.scanner_output.has_git %} ({{ report.scanner_output.commit_count }} commits, last: {{ report.scanner_output.last_commit_date[:10] }}){% endif %}</td></tr>
  <tr><td>Working Tree</td><td>{{ "Dirty" if report.scanner_output.dirty else "Clean" }}{% if report.scanner_output.dirty %} ({{ report.scanner_output.modified_count }} mod, {{ report.scanner_output.untracked_count }} untracked, {{ report.scanner_output.staged_count }} staged){% endif %}</td></tr>
  <tr><td>Files</td><td>{{ report.scanner_output.total_files }} files, {{ report.scanner_output.total_dirs }} dirs, {{ "%.1f"|format(report.scanner_output.total_size_bytes / 1048576) }} MB</td></tr>
  <tr><td>Monorepo</td><td>{{ "Yes" if report.scanner_output.monorepo_signal else "No" }}</td></tr>
  <tr><td>GitNexus</td><td>{{ "Yes (%d symbols, %d flows)"|format(report.scanner_output.gitnexus_symbols, report.scanner_output.gitnexus_flows) if report.scanner_output.has_gitnexus else "No" }}</td></tr>
</table>
</div>

<!-- ===== PURPOSE ===== -->
<div class="section" id="purpose">
<h2>3. Purpose</h2>
<div class="finding evidence">
  <span class="badge conf-{{ report.purpose.confidence }}">{{ confidence_badge(report.purpose.confidence) }}</span>
  <p style="margin-top:0.5em;">{{ report.purpose.summary }}</p>
  {% if report.purpose.details %}<p style="color:#8b949e;font-size:0.9em;">{{ report.purpose.details }}</p>{% endif %}
  {% if report.purpose.assumptions %}
    <p class="assumption-tag">Assumptions: {{ report.purpose.assumptions | join("; ") }}</p>
  {% endif %}
  {% if report.purpose.evidence %}
    <div class="rec-evidence">Evidence: {{ report.purpose.evidence | map("evidence_link") | join(", ") }}</div>
  {% endif %}
</div>
</div>

<!-- ===== ANALYSIS DIMENSIONS ===== -->
<div class="section" id="dimensions">
<h2>4. Analysis Dimensions</h2>
<table>
  <tr><th>Dimension</th><th>Confidence</th><th>Assessment</th></tr>
  {% for dim in report.dimensions %}
  <tr>
    <td style="white-space:nowrap;">{{ dim.dimension | replace("_", " ") | title }}</td>
    <td><span class="badge" style="background:{{ confidence_color(dim.confidence) }}20;color:{{ confidence_color(dim.confidence) }};border:1px solid {{ confidence_color(dim.confidence) }};">{{ confidence_badge(dim.confidence) }}</span></td>
    <td>{{ dim.summary[:200] }}{% if dim.summary|length > 200 %}&hellip;{% endif %}</td>
  </tr>
  {% endfor %}
</table>
</div>

<!-- ===== SECURITY NOTES ===== -->
<div class="section" id="security">
<h2>5. Security Notes</h2>
{% if report.security_notes %}
  {% for note in report.security_notes %}
    <div class="security-note">{{ note }}</div>
  {% endfor %}
{% else %}
  <p>No security notes.</p>
{% endif %}
{% if report.scanner_output.secret_files_detected %}
  <div class="security-note">
    <strong>Secret files detected (contents NOT inspected):</strong>
    <ul style="margin:0.3em 0 0 0;">
      {% for sf in report.scanner_output.secret_files_detected %}
        <li><code>{{ sf }}</code></li>
      {% endfor %}
    </ul>
  </div>
{% endif %}
</div>

<!-- ===== CONTRADICTIONS & UNKNOWNS ===== -->
<div class="section" id="contradictions">
<h2>6. Contradictions &amp; Unknowns</h2>

{% if report.contradictions %}
<h3>Contradictions</h3>
{% for c in report.contradictions %}
<div class="finding assumption">
  <strong>{{ c.dimension | replace("_", " ") | title }}</strong>
  <p style="margin:0.3em 0;">{{ c.description }}</p>
  <p style="font-size:0.85em;color:#8b949e;">Sources: {{ c.sources | join(", ") }}</p>
  {% if c.resolution %}<p style="font-size:0.85em;color:#3fb950;">Resolution: {{ c.resolution }}</p>{% endif %}
</div>
{% endfor %}
{% else %}
<p>No contradictions found.</p>
{% endif %}

{% if report.unknowns %}
<h3>Unknowns</h3>
{% for u in report.unknowns %}
<div class="unknown-box">
  <strong>{{ u.dimension | replace("_", " ") | title }}</strong>
  <span class="badge" style="background:#8b949e20;color:#8b949e;border:1px solid #8b949e;">{{ confidence_badge(u.confidence) }}</span>
  <p style="margin:0.3em 0;">{{ u.summary }}</p>
  {% if u.details %}<p style="font-size:0.85em;color:#8b949e;">{{ u.details }}</p>{% endif %}
</div>
{% endfor %}
{% else %}
<p>No unknown areas.</p>
{% endif %}
</div>

<!-- ===== RECOMMENDATIONS ===== -->
<div class="section" id="recommendations">
<h2>7. Recommendations</h2>
{% if report.recommendations %}
  {% for rec in report.recommendations %}
  <div class="rec-card">
    <div class="rec-header">
      <span class="rec-title">{{ rec.action }}</span>
      <span>
        {{ priority_badge(rec.priority) }}
        {{ priority_badge(rec.category) }}
        <span class="badge" style="background:#30363d40;color:#8b949e;border:1px solid #484f58;">{{ rec.estimated_effort }}</span>
      </span>
    </div>
    <p style="margin:0.5em 0;font-size:0.92em;">{{ rec.justification }}</p>
    {% if rec.risks_of_inaction %}<p class="rec-risks">Risks of inaction: {{ rec.risks_of_inaction }}</p>{% endif %}
    {% if rec.evidence %}<div class="rec-evidence">Evidence: {{ rec.evidence | map("evidence_link") | join(", ") }}</div>{% endif %}
    {% if rec.assumptions %}<p class="assumption-tag" style="margin-top:0.3em;">Assumptions: {{ rec.assumptions | join("; ") }}</p>{% endif %}
  </div>
  {% endfor %}
{% else %}
<p>No recommendations generated.</p>
{% endif %}
</div>

<!-- ===== NEXT ACTIONS ===== -->
<div class="section" id="next-actions">
<h2>8. Next Actions</h2>
{% if report.next_actions %}
  {% for action in report.next_actions %}
    <div class="next-action">{{ loop.index }}. {{ action }}</div>
  {% endfor %}
{% else %}
<p>No specific next actions.</p>
{% endif %}
</div>

<!-- ===== EVIDENCE REGISTRY ===== -->
<div class="section" id="evidence">
<h2>9. Evidence Registry</h2>
{% if report.evidence_registry %}
<table>
  <tr><th>ID</th><th>Type</th><th>Description</th></tr>
  {% for eid, es in report.evidence_registry.items() %}
  <tr>
    <td><code class="evidence-ref">{{ eid }}</code></td>
    <td>{{ es.type }}</td>
    <td>{{ es.description }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>No evidence registered.</p>
{% endif %}
</div>

<!-- ===== APPENDIX ===== -->
<div class="section" id="appendix">
<h2>10. Appendix</h2>

<h3>Scanner Summary</h3>
<table>
  <tr><td>Languages</td><td>{{ report.scanner_output.languages | dictsort(false, "value") | reverse | map("join", ": ") | join(", ") }}</td></tr>
  <tr><td>Build Systems</td><td>{{ report.scanner_output.build_systems | join(", ") or "None detected" }}</td></tr>
  <tr><td>Test Frameworks</td><td>{{ report.scanner_output.test_frameworks | join(", ") or "None detected" }}</td></tr>
  <tr><td>Entrypoints</td><td>{{ report.scanner_output.entrypoints | join(", ") or "None detected" }}</td></tr>
  <tr><td>Dependency Files</td><td>{{ report.scanner_output.dependency_files | join(", ") or "None" }}</td></tr>
  <tr><td>CI/CD</td><td>{{ report.scanner_output.ci_cd_files | join(", ") or "None" }}</td></tr>
  <tr><td>Docker</td><td>{{ report.scanner_output.docker_files | join(", ") or "None" }}</td></tr>
  <tr><td>Documentation</td><td>{{ report.scanner_output.documentation_files | join(", ") or "None" }}</td></tr>
</table>

{% if report.subagent_summaries %}
<h3>Subagent Summaries</h3>
{% for summary in report.subagent_summaries %}
<pre>{{ summary }}</pre>
{% endfor %}
{% endif %}
</div>

<!-- ===== FOOTER ===== -->
<div class="footer">
  <p>
    Generated by <strong>Repo Oracle</strong> on {{ report.metadata.analysis_timestamp }}<br>
    Hermes {{ report.metadata.hermes_version }} &middot; Analysis tier: {{ report.metadata.analysis_tier }} &middot;
    Tool calls: {{ report.metadata.total_tool_calls }} &middot;
    GitNexus: {{ "enabled" if report.metadata.gitnexus_used else "not used" }}<br>
    <a href="./{{ report_filename_json }}">View raw JSON</a>
  </p>
</div>

</body>
</html>"""


# ── Jinja2 Filter Helpers ───────────────────────────────────────────────────

def _confidence_color(confidence: str) -> str:
    return CONFIDENCE_COLORS.get(confidence, "#8b949e")


def _evidence_link(eid: str) -> str:
    return f'<code class="evidence-ref">{eid}</code>'


# ── Render Function ─────────────────────────────────────────────────────────

def render_report(report: dict, json_filename: str = "") -> str:
    """Render a Report dict to standalone HTML string."""
    template = Template(HTML_TEMPLATE)

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
