"""repo-oracle — Investigate any Git repository with one command.

Public API:
    from repo_oracle import scan_repo, build_report, render_html, write_reports
"""

from repo_oracle.scanner import scan_repo
from repo_oracle.schema import (
    Report,
    Finding,
    Recommendation,
    EvidenceSource,
    Contradiction,
    ReportMetadata,
    ScannerOutput,
    validate_report,
    validate_report_strict,
    generate_json_schema,
    empty_report,
    new_finding,
    new_recommendation,
    new_evidence,
    new_metadata,
    ALL_DIMENSIONS,
    DIMENSION_NAMES,
    META_DIMENSIONS,
)
from repo_oracle.render import render_report, render_markdown
from repo_oracle.writer import write_reports

__version__ = "0.1.0"
__all__ = [
    "scan_repo",
    "render_report",
    "render_markdown",
    "write_reports",
    "validate_report",
    "validate_report_strict",
    "generate_json_schema",
    "empty_report",
    "new_finding",
    "new_recommendation",
    "new_evidence",
    "new_metadata",
    "Report",
    "Finding",
    "Recommendation",
    "EvidenceSource",
    "Contradiction",
    "ReportMetadata",
    "ScannerOutput",
    "ALL_DIMENSIONS",
    "DIMENSION_NAMES",
    "META_DIMENSIONS",
]
