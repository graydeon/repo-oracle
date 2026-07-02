"""Tests for repo-oracle renderer module."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from render import (
    render_report,
    _confidence_badge,
    _confidence_color,
    _priority_badge,
    _activity_badge,
    CONFIDENCE_BADGES,
    PRIORITY_COLORS,
    ACTIVITY_COLORS,
)
from schema import empty_report, new_finding, new_recommendation, new_evidence, ALL_DIMENSIONS


def _make_test_report() -> dict:
    """Build a comprehensive test report for rendering."""
    report = empty_report("/tmp/test-project", "test-project", "test-project")
    report["executive_summary"] = "A test project used for renderer verification. This project demonstrates various report features including findings, recommendations, security notes, and unknowns."
    report["purpose"] = new_finding(
        "purpose", "HIGH",
        "Test project for rendering validation",
        ["scan:readme", "scan:main.py"],
        "The project contains a main.py entrypoint and comprehensive README explaining its purpose."
    )
    report["purpose"]["assumptions"] = ["Assumed Python 3.11+ is the target runtime"]

    report["vital_signs"] = {
        "activity": "DORMANT",
        "language": "Python",
        "build_system": "setuptools",
    }

    # Populate dimensions
    for i, dim in enumerate(ALL_DIMENSIONS):
        conf = "HIGH" if i < 5 else "MEDIUM" if i < 12 else "LOW"
        report["dimensions"][i] = new_finding(
            dim, conf,
            f"Assessment for {dim}",
            [f"scan:dim:{dim}"],
            f"Detailed analysis of {dim}."
        )
    # Mark one as N/A
    report["dimensions"][-1]["confidence"] = "N/A"

    # Evidence registry
    report["evidence_registry"] = {
        "scan:readme": new_evidence("scan:readme", "scan", "README.md describes the project"),
        "scan:main.py": new_evidence("scan:main.py", "scan", "Entrypoint at main.py:1-10"),
    }
    for dim in ALL_DIMENSIONS:
        report["evidence_registry"][f"scan:dim:{dim}"] = new_evidence(
            f"scan:dim:{dim}", "scan", f"Evidence for {dim}")

    # Recommendations
    report["recommendations"] = [
        new_recommendation(
            "rec-1", "DOCUMENT", "MEDIUM", "Add architecture documentation",
            "The project lacks an ARCHITECTURE.md file describing component layout.",
            ["scan:dim:documentation_quality"],
            "SMALL", "New contributors will struggle to understand the codebase.",
        ),
        new_recommendation(
            "rec-2", "DEPENDENCY-UPDATE", "HIGH", "Update stale dependencies",
            "pyproject.toml pins packages to versions over 2 years old.",
            ["scan:dim:stale_dependencies"],
            "MEDIUM", "Security vulnerabilities may exist in outdated packages.",
            ["Assumes pip install still works for pinned versions"],
        ),
    ]

    # Security notes
    report["security_notes"] = [
        "No hardcoded API keys detected in source files.",
        "No authentication middleware found — may be internal-only tool.",
    ]

    # Contradictions
    report["contradictions"] = [
        {
            "dimension": "purpose",
            "sources": ["scan:readme", "scan:main.py"],
            "description": "README claims this is a CLI tool but main.py imports Flask web framework.",
            "resolution": "Likely a web app with CLI management commands. README is stale.",
        },
    ]

    # Unknowns
    report["unknowns"] = [
        new_finding(
            "deployment_clues", "UNKNOWN",
            "No Dockerfiles, CI/CD configs, or hosting configurations found.",
            [],
            "The project may be run locally only, or deployment configuration lives outside this repo.",
        ),
    ]

    # Next actions
    report["next_actions"] = [
        "Write ARCHITECTURE.md documenting component layout.",
        "Run `pip list --outdated` and update dependencies.",
        "Determine deployment target and add Dockerfile.",
    ]

    # Scanner output tweaks
    report["scanner_output"]["commit_count"] = 42
    report["scanner_output"]["last_commit_date"] = "2026-01-15T12:00:00+00:00"
    report["scanner_output"]["dirty"] = True
    report["scanner_output"]["modified_count"] = 3
    report["scanner_output"]["total_files"] = 156
    report["scanner_output"]["total_dirs"] = 23
    report["scanner_output"]["total_size_bytes"] = 5242880
    report["scanner_output"]["has_git"] = True
    report["scanner_output"]["has_gitnexus"] = True
    report["scanner_output"]["gitnexus_symbols"] = 1240
    report["scanner_output"]["gitnexus_flows"] = 84
    report["scanner_output"]["secret_files_detected"] = [".env", "config/credentials.yaml"]
    report["scanner_output"]["languages"] = {"Python": 120, "JavaScript": 25, "HTML": 11}
    report["scanner_output"]["build_systems"] = ["Python (setuptools/poetry/hatch)"]
    report["scanner_output"]["entrypoints"] = ["main.py", "app.py"]
    report["scanner_output"]["dependency_files"] = ["pyproject.toml"]

    # Subagent summaries
    report["subagent_summaries"] = [
        "Git history analysis: 42 commits by 3 contributors. Last active Jan 2026.",
    ]

    return report


class TestBadgeHelpers:
    def test_confidence_badge_high(self):
        assert "HIGH" in _confidence_badge("HIGH")

    def test_confidence_badge_unknown(self):
        assert "UNKNOWN" in _confidence_badge("UNKNOWN")

    def test_confidence_color_high(self):
        assert _confidence_color("HIGH") == "#3fb950"

    def test_confidence_color_na(self):
        assert _confidence_color("N/A") == "#484f58"

    def test_priority_badge_urgent(self):
        badge = _priority_badge("URGENT")
        assert "URGENT" in badge
        assert "f85149" in badge

    def test_activity_badge_active(self):
        badge = _activity_badge("ACTIVE")
        assert "ACTIVE" in badge


class TestRenderReport:
    def test_renders_valid_html(self):
        report = _make_test_report()
        html = render_report(report, "test-report.json")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_renders_report_source(self):
        report = _make_test_report()
        html = render_report(report, "my-report.json")
        assert 'href="./my-report.json"' in html

    def test_contains_all_sections(self):
        report = _make_test_report()
        html = render_report(report)
        sections = [
            "Executive Summary",
            "Vital Signs",
            "Purpose",
            "Analysis Dimensions",
            "Security Notes",
            "Contradictions",
            "Recommendations",
            "Next Actions",
            "Evidence Registry",
            "Appendix",
        ]
        for section in sections:
            assert section in html, f"Missing section: {section}"

    def test_renders_all_dimensions(self):
        report = _make_test_report()
        html = render_report(report)
        for dim in ALL_DIMENSIONS:
            title = dim.replace("_", " ").title()
            assert title in html, f"Missing dimension: {title}"

    def test_renders_recommendations(self):
        report = _make_test_report()
        html = render_report(report)
        assert "Add architecture documentation" in html
        assert "Update stale dependencies" in html
        assert "MEDIUM" in html  # Effort badge

    def test_renders_security_notes(self):
        report = _make_test_report()
        html = render_report(report)
        assert "No hardcoded API keys" in html
        assert ".env" in html
        assert "config/credentials.yaml" in html
        assert "contents NOT inspected" in html.lower() or "NOT inspected" in html

    def test_renders_empty_report(self):
        report = empty_report("/tmp/empty", "empty", "empty")
        html = render_report(report)
        assert "<!DOCTYPE html>" in html
        assert "empty" in html

    def test_output_to_file(self):
        report = _make_test_report()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            f.write(render_report(report, "test.json"))
            path = f.name
        try:
            assert os.path.getsize(path) > 5000, f"HTML file too small: {os.path.getsize(path)} bytes"
        finally:
            os.unlink(path)
