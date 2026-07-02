"""Repo Oracle — Canonical Report Schema.

TypedDict definitions, JSON Schema generation, and validation.
Every finding is evidence-linked. Confidence is explicit.
"""

from __future__ import annotations

import json
from typing import Literal, Optional, TypedDict

# ── Confidence & Priority Literals ──────────────────────────────────────────

Confidence = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN", "N/A"]
Priority = Literal["URGENT", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]
Effort = Literal["TRIVIAL", "SMALL", "MEDIUM", "LARGE"]
Tier = Literal["QUICK", "DEEP", "EXHAUSTIVE"]

RecommendationCategory = Literal[
    "REVIVE",
    "ARCHIVE",
    "DOCUMENT",
    "TEST-FIRST-REPAIR",
    "DEPENDENCY-UPDATE",
    "SECURITY-HARDENING",
    "EXTRACT-CODE",
    "REWRITE",
    "DELETE-CANDIDATE",
    "PRODUCTIZE",
    "MAINTAIN-AS-IS",
]

EvidenceType = Literal["file", "git", "scan", "web", "inference"]

# ── Dimension Names ─────────────────────────────────────────────────────────

DIMENSION_NAMES: list[str] = [
    "purpose",
    "languages_and_frameworks",
    "build_and_test_system",
    "entrypoints",
    "architecture",
    "dependency_graph",
    "runtime_assumptions",
    "stale_dependencies",
    "git_history",
    "open_todos",
    "documentation_quality",
    "test_coverage",
    "security_surface",
    "deployment_clues",
]

META_DIMENSIONS: list[str] = [
    "activity_signal",
    "value_assessment",
    "next_action_recommendation",
]

ALL_DIMENSIONS: list[str] = DIMENSION_NAMES + META_DIMENSIONS

# ── TypedDicts ──────────────────────────────────────────────────────────────


class EvidenceSource(TypedDict):
    id: str  # e.g. "file:src/main.py:1-50"
    type: EvidenceType  # file, git, scan, web, inference
    description: str


class Finding(TypedDict):
    dimension: str
    confidence: Confidence
    summary: str
    evidence: list[str]  # EvidenceSource IDs
    details: str
    assumptions: list[str]


class Recommendation(TypedDict):
    id: str
    category: RecommendationCategory
    priority: Priority
    action: str
    justification: str
    evidence: list[str]
    estimated_effort: Effort
    risks_of_inaction: str
    assumptions: list[str]


class Contradiction(TypedDict):
    dimension: str
    sources: list[str]
    description: str
    resolution: Optional[str]


class ReportMetadata(TypedDict):
    repo_path: str
    repo_name: str
    repo_slug: str
    analysis_timestamp: str  # ISO 8601
    hermes_version: str
    gitnexus_used: bool
    analysis_tier: Tier
    total_tool_calls: int
    analysis_duration_seconds: float


class ScannerOutput(TypedDict):
    """Deterministic scanner output. See scanner.py for the full contract."""

    repo_path: str
    repo_name: str
    repo_slug: str
    has_git: bool
    has_gitnexus: bool
    gitnexus_symbols: int
    gitnexus_flows: int
    gitnexus_top_symbols: list[str]
    git_branch: str
    git_remote: str
    last_commit_date: str
    last_commit_hash: str
    commit_count: int
    contributors: list[str]
    dirty: bool
    untracked_count: int
    modified_count: int
    staged_count: int
    languages: dict[str, int]  # language → file count
    build_systems: list[str]
    test_frameworks: list[str]
    entrypoints: list[str]
    total_files: int
    total_dirs: int
    total_size_bytes: int
    excluded_count: int
    secret_files_detected: list[str]  # paths only, contents never read
    monorepo_signal: bool
    top_level_dirs: list[str]
    dependency_files: list[str]
    ci_cd_files: list[str]
    docker_files: list[str]
    documentation_files: list[str]
    error: Optional[str]


class Report(TypedDict):
    metadata: ReportMetadata
    executive_summary: str
    purpose: Finding
    vital_signs: dict  # activity, language, build_system
    dimensions: list[Finding]  # All 14 analysis + 3 meta dimensions
    evidence_registry: dict[str, EvidenceSource]
    contradictions: list[Contradiction]
    unknowns: list[Finding]
    security_notes: list[str]
    recommendations: list[Recommendation]
    next_actions: list[str]  # Ordered, actionable
    scanner_output: ScannerOutput
    subagent_summaries: list[str]


# ── Validation ──────────────────────────────────────────────────────────────

VALID_CONFIDENCES: set[str] = {"HIGH", "MEDIUM", "LOW", "UNKNOWN", "N/A"}
VALID_PRIORITIES: set[str] = {"URGENT", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
VALID_EFFORTS: set[str] = {"TRIVIAL", "SMALL", "MEDIUM", "LARGE"}
VALID_TIERS: set[str] = {"QUICK", "DEEP", "EXHAUSTIVE"}
VALID_CATEGORIES: set[str] = {
    "REVIVE",
    "ARCHIVE",
    "DOCUMENT",
    "TEST-FIRST-REPAIR",
    "DEPENDENCY-UPDATE",
    "SECURITY-HARDENING",
    "EXTRACT-CODE",
    "REWRITE",
    "DELETE-CANDIDATE",
    "PRODUCTIZE",
    "MAINTAIN-AS-IS",
}
VALID_EVIDENCE_TYPES: set[str] = {"file", "git", "scan", "web", "inference"}


class ValidationError(ValueError):
    """Raised when a report fails schema validation."""

    pass


def validate_report(report: Report) -> list[str]:
    """Validate a Report dict against the schema. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    # Metadata
    meta = report.get("metadata", {})
    if not isinstance(meta, dict):
        errors.append("metadata: missing or not a dict")
    else:
        for field in (
            "repo_path",
            "repo_name",
            "repo_slug",
            "analysis_timestamp",
            "hermes_version",
            "analysis_tier",
        ):
            if field not in meta:
                errors.append(f"metadata.{field}: missing")
        if meta.get("analysis_tier") not in VALID_TIERS:
            errors.append(
                f"metadata.analysis_tier: invalid tier '{meta.get('analysis_tier')}'"
            )
        if not isinstance(meta.get("gitnexus_used"), bool):
            errors.append("metadata.gitnexus_used: must be bool")
        if not isinstance(meta.get("total_tool_calls"), int):
            errors.append("metadata.total_tool_calls: must be int")
        if not isinstance(meta.get("analysis_duration_seconds"), (int, float)):
            errors.append("metadata.analysis_duration_seconds: must be number")

    # Executive summary
    if not isinstance(report.get("executive_summary"), str):
        errors.append("executive_summary: missing or not a string")

    # Purpose
    _validate_finding(report.get("purpose"), "purpose", errors)

    # Vital signs
    vitals = report.get("vital_signs", {})
    if not isinstance(vitals, dict):
        errors.append("vital_signs: missing or not a dict")
    else:
        for key in ("activity", "language", "build_system"):
            if key not in vitals:
                errors.append(f"vital_signs.{key}: missing")

    # Dimensions (must have all 14 + 3 meta)
    dimensions = report.get("dimensions", [])
    if not isinstance(dimensions, list):
        errors.append("dimensions: missing or not a list")
    else:
        dim_names = [d.get("dimension", "") for d in dimensions]
        for expected in ALL_DIMENSIONS:
            if expected not in dim_names:
                errors.append(f"dimensions: missing dimension '{expected}'")
        for i, dim in enumerate(dimensions):
            _validate_finding(dim, f"dimensions[{i}]", errors)

    # Evidence registry
    registry = report.get("evidence_registry", {})
    if not isinstance(registry, dict):
        errors.append("evidence_registry: missing or not a dict")
    else:
        for eid, es in registry.items():
            if not isinstance(es, dict):
                errors.append(f"evidence_registry['{eid}']: not a dict")
                continue
            if es.get("type") not in VALID_EVIDENCE_TYPES:
                errors.append(
                    f"evidence_registry['{eid}'].type: invalid '{es.get('type')}'"
                )

    # Contradictions
    contradictions = report.get("contradictions", [])
    if not isinstance(contradictions, list):
        errors.append("contradictions: missing or not a list")

    # Unknowns
    unknowns = report.get("unknowns", [])
    if not isinstance(unknowns, list):
        errors.append("unknowns: missing or not a list")

    # Security notes
    sec_notes = report.get("security_notes", [])
    if not isinstance(sec_notes, list):
        errors.append("security_notes: missing or not a list")

    # Recommendations
    recs = report.get("recommendations", [])
    if not isinstance(recs, list):
        errors.append("recommendations: missing or not a list")
    else:
        for i, rec in enumerate(recs):
            _validate_recommendation(rec, f"recommendations[{i}]", errors)

    # Next actions
    actions = report.get("next_actions", [])
    if not isinstance(actions, list):
        errors.append("next_actions: missing or not a list")

    # Scanner output
    scanner = report.get("scanner_output", {})
    if not isinstance(scanner, dict):
        errors.append("scanner_output: missing or not a dict")

    # Subagent summaries
    summaries = report.get("subagent_summaries", [])
    if not isinstance(summaries, list):
        errors.append("subagent_summaries: missing or not a list")

    return errors


def validate_report_strict(report: Report) -> None:
    """Validate and raise ValidationError if any errors found."""
    errors = validate_report(report)
    if errors:
        raise ValidationError(
            f"Report validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def _validate_finding(finding: object, path: str, errors: list[str]) -> None:
    if not isinstance(finding, dict):
        errors.append(f"{path}: not a dict")
        return
    if finding.get("confidence") not in VALID_CONFIDENCES:
        errors.append(f"{path}.confidence: invalid '{finding.get('confidence')}'")
    if not isinstance(finding.get("dimension"), str):
        errors.append(f"{path}.dimension: missing or not a string")
    if not isinstance(finding.get("summary"), str):
        errors.append(f"{path}.summary: missing or not a string")
    if not isinstance(finding.get("evidence"), list):
        errors.append(f"{path}.evidence: missing or not a list")


def _validate_recommendation(rec: object, path: str, errors: list[str]) -> None:
    if not isinstance(rec, dict):
        errors.append(f"{path}: not a dict")
        return
    if not isinstance(rec.get("id"), str):
        errors.append(f"{path}.id: missing or not a string")
    if rec.get("category") not in VALID_CATEGORIES:
        errors.append(f"{path}.category: invalid '{rec.get('category')}'")
    if rec.get("priority") not in VALID_PRIORITIES:
        errors.append(f"{path}.priority: invalid '{rec.get('priority')}'")
    if rec.get("estimated_effort") not in VALID_EFFORTS:
        errors.append(
            f"{path}.estimated_effort: invalid '{rec.get('estimated_effort')}'"
        )
    if not isinstance(rec.get("evidence"), list):
        errors.append(f"{path}.evidence: missing or not a list")
    if not rec.get("evidence"):
        errors.append(f"{path}.evidence: must have at least one evidence source")
    if not isinstance(rec.get("action"), str):
        errors.append(f"{path}.action: missing or not a string")


# ── JSON Schema Generation ──────────────────────────────────────────────────


def generate_json_schema() -> dict:
    """Generate a JSON Schema (draft-07) for Report validation."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://repo-oracle.home.arpa/schema/report.json",
        "title": "Repo Oracle Report",
        "description": "Canonical schema for repo-oracle investigation reports",
        "type": "object",
        "required": [
            "metadata",
            "executive_summary",
            "purpose",
            "vital_signs",
            "dimensions",
            "evidence_registry",
            "contradictions",
            "unknowns",
            "security_notes",
            "recommendations",
            "next_actions",
            "scanner_output",
            "subagent_summaries",
        ],
        "properties": {
            "metadata": {
                "type": "object",
                "required": [
                    "repo_path",
                    "repo_name",
                    "repo_slug",
                    "analysis_timestamp",
                    "hermes_version",
                    "gitnexus_used",
                    "analysis_tier",
                    "total_tool_calls",
                    "analysis_duration_seconds",
                ],
                "properties": {
                    "repo_path": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "repo_slug": {"type": "string"},
                    "analysis_timestamp": {"type": "string", "format": "date-time"},
                    "hermes_version": {"type": "string"},
                    "gitnexus_used": {"type": "boolean"},
                    "analysis_tier": {"enum": list(VALID_TIERS)},
                    "total_tool_calls": {"type": "integer", "minimum": 0},
                    "analysis_duration_seconds": {"type": "number", "minimum": 0},
                },
            },
            "executive_summary": {"type": "string"},
            "purpose": {"$ref": "#/$defs/finding"},
            "vital_signs": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string"},
                    "language": {"type": "string"},
                    "build_system": {"type": "string"},
                },
            },
            "dimensions": {
                "type": "array",
                "minItems": len(ALL_DIMENSIONS),
                "items": {"$ref": "#/$defs/finding"},
            },
            "evidence_registry": {
                "type": "object",
                "additionalProperties": {"$ref": "#/$defs/evidence_source"},
            },
            "contradictions": {
                "type": "array",
                "items": {"$ref": "#/$defs/contradiction"},
            },
            "unknowns": {
                "type": "array",
                "items": {"$ref": "#/$defs/finding"},
            },
            "security_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recommendations": {
                "type": "array",
                "items": {"$ref": "#/$defs/recommendation"},
            },
            "next_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "scanner_output": {"type": "object"},
            "subagent_summaries": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "$defs": {
            "finding": {
                "type": "object",
                "required": [
                    "dimension",
                    "confidence",
                    "summary",
                    "evidence",
                    "details",
                    "assumptions",
                ],
                "properties": {
                    "dimension": {"type": "string"},
                    "confidence": {"enum": list(VALID_CONFIDENCES)},
                    "summary": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "details": {"type": "string"},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                },
            },
            "evidence_source": {
                "type": "object",
                "required": ["id", "type", "description"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"enum": list(VALID_EVIDENCE_TYPES)},
                    "description": {"type": "string"},
                },
            },
            "recommendation": {
                "type": "object",
                "required": [
                    "id",
                    "category",
                    "priority",
                    "action",
                    "justification",
                    "evidence",
                    "estimated_effort",
                    "risks_of_inaction",
                    "assumptions",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "category": {"enum": list(VALID_CATEGORIES)},
                    "priority": {"enum": list(VALID_PRIORITIES)},
                    "action": {"type": "string"},
                    "justification": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "estimated_effort": {"enum": list(VALID_EFFORTS)},
                    "risks_of_inaction": {"type": "string"},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                },
            },
            "contradiction": {
                "type": "object",
                "required": ["dimension", "sources", "description", "resolution"],
                "properties": {
                    "dimension": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "resolution": {"type": ["string", "null"]},
                },
            },
        },
    }


# ── Convenience ─────────────────────────────────────────────────────────────


def report_to_json(report: Report, indent: int = 2) -> str:
    """Serialize a Report to JSON string."""
    return json.dumps(report, indent=indent, ensure_ascii=False)


def report_from_json(data: str) -> Report:
    """Deserialize a Report from JSON string."""
    return json.loads(data)


def new_metadata(
    repo_path: str,
    repo_name: str,
    repo_slug: str,
    hermes_version: str = "unknown",
    analysis_tier: Tier = "DEEP",
) -> ReportMetadata:
    """Create a ReportMetadata with defaults."""
    from datetime import datetime, timezone

    return ReportMetadata(
        repo_path=repo_path,
        repo_name=repo_name,
        repo_slug=repo_slug,
        analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        hermes_version=hermes_version,
        gitnexus_used=False,
        analysis_tier=analysis_tier,
        total_tool_calls=0,
        analysis_duration_seconds=0.0,
    )


def new_finding(
    dimension: str,
    confidence: Confidence = "UNKNOWN",
    summary: str = "",
    evidence: list[str] | None = None,
    details: str = "",
    assumptions: list[str] | None = None,
) -> Finding:
    """Create a Finding with defaults."""
    return Finding(
        dimension=dimension,
        confidence=confidence,
        summary=summary,
        evidence=evidence or [],
        details=details,
        assumptions=assumptions or [],
    )


def new_evidence(id: str, type: EvidenceType, description: str = "") -> EvidenceSource:
    """Create an EvidenceSource."""
    return EvidenceSource(id=id, type=type, description=description)


def new_recommendation(
    id: str,
    category: RecommendationCategory,
    priority: Priority = "MEDIUM",
    action: str = "",
    justification: str = "",
    evidence: list[str] | None = None,
    estimated_effort: Effort = "MEDIUM",
    risks_of_inaction: str = "",
    assumptions: list[str] | None = None,
) -> Recommendation:
    """Create a Recommendation with defaults."""
    return Recommendation(
        id=id,
        category=category,
        priority=priority,
        action=action,
        justification=justification,
        evidence=evidence or [],
        estimated_effort=estimated_effort,
        risks_of_inaction=risks_of_inaction,
        assumptions=assumptions or [],
    )


def empty_report(
    repo_path: str,
    repo_name: str = "",
    repo_slug: str = "",
) -> Report:
    """Create an empty but valid Report skeleton for a repo."""
    if not repo_slug:
        import re

        repo_slug = re.sub(r"[^a-z0-9]+", "-", (repo_name or "unknown").lower()).strip(
            "-"
        )

    return Report(
        metadata=new_metadata(repo_path, repo_name or repo_path, repo_slug),
        executive_summary="",
        purpose=new_finding("purpose"),
        vital_signs={
            "activity": "UNKNOWN",
            "language": "UNKNOWN",
            "build_system": "UNKNOWN",
        },
        dimensions=[new_finding(dim) for dim in ALL_DIMENSIONS],
        evidence_registry={},
        contradictions=[],
        unknowns=[],
        security_notes=[],
        recommendations=[],
        next_actions=[],
        scanner_output=ScannerOutput(
            repo_path=repo_path,
            repo_name=repo_name or repo_path,
            repo_slug=repo_slug,
            has_git=False,
            has_gitnexus=False,
            gitnexus_symbols=0,
            gitnexus_flows=0,
            gitnexus_top_symbols=[],
            git_branch="",
            git_remote="",
            last_commit_date="",
            last_commit_hash="",
            commit_count=0,
            contributors=[],
            dirty=False,
            untracked_count=0,
            modified_count=0,
            staged_count=0,
            languages={},
            build_systems=[],
            test_frameworks=[],
            entrypoints=[],
            total_files=0,
            total_dirs=0,
            total_size_bytes=0,
            excluded_count=0,
            secret_files_detected=[],
            monorepo_signal=False,
            top_level_dirs=[],
            dependency_files=[],
            ci_cd_files=[],
            docker_files=[],
            documentation_files=[],
            error=None,
        ),
        subagent_summaries=[],
    )
