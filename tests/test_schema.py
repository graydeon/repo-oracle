"""Tests for repo-oracle schema module."""

import json
import pytest
from repo_oracle.schema import (
    Report,
    validate_report,
    validate_report_strict,
    ValidationError,
    generate_json_schema,
    empty_report,
    new_finding,
    new_evidence,
    new_recommendation,
    ALL_DIMENSIONS,
    DIMENSION_NAMES,
    META_DIMENSIONS,
    VALID_CONFIDENCES,
    VALID_CATEGORIES,
)


def _make_valid_report() -> Report:
    """Build a minimal valid report for testing."""
    report = empty_report("/tmp/test-repo", "test-repo", "test-repo")
    report["executive_summary"] = "A test repository."
    report["purpose"] = new_finding(
        "purpose",
        "HIGH",
        "Test repo for schema validation",
        ["scan:language"],
        "A test project.",
    )
    report["vital_signs"] = {
        "activity": "DORMANT",
        "language": "Python",
        "build_system": "setuptools",
    }

    # Populate all dimensions
    for i, dim in enumerate(ALL_DIMENSIONS):
        report["dimensions"][i] = new_finding(
            dim,
            "MEDIUM",
            f"Assessment of {dim}",
            [f"scan:dim:{dim}"],
            f"Details for {dim}",
        )

    report["evidence_registry"] = {
        "scan:language": new_evidence(
            "scan:language", "scan", "Scanner detected Python"
        ),
        "scan:dim:purpose": new_evidence("scan:dim:purpose", "scan", "Scanner output"),
    }
    for dim in ALL_DIMENSIONS:
        report["evidence_registry"][f"scan:dim:{dim}"] = new_evidence(
            f"scan:dim:{dim}", "scan", f"Evidence for {dim}"
        )

    report["recommendations"] = [
        new_recommendation(
            "rec-1",
            "DOCUMENT",
            "MEDIUM",
            "Add a README",
            "No README found",
            ["scan:dim:documentation_quality"],
            "SMALL",
            "Project remains undiscoverable",
        ),
    ]
    report["next_actions"] = ["Write README.md", "Add CI pipeline"]
    report["security_notes"] = ["No secret files detected"]
    return report


class TestConstants:
    def test_dimension_counts(self):
        assert len(DIMENSION_NAMES) == 14, (
            "Must have exactly 14 core analysis dimensions"
        )
        assert len(META_DIMENSIONS) == 3, "Must have exactly 3 meta dimensions"
        assert len(ALL_DIMENSIONS) == 17

    def test_confidence_values(self):
        assert VALID_CONFIDENCES == {"HIGH", "MEDIUM", "LOW", "UNKNOWN", "N/A"}

    def test_categories(self):
        assert len(VALID_CATEGORIES) == 11


class TestEmptyReport:
    def test_has_all_dimensions(self):
        report = empty_report("/tmp/foo", "foo", "foo")
        dim_names = [d["dimension"] for d in report["dimensions"]]
        for expected in ALL_DIMENSIONS:
            assert expected in dim_names, f"Missing dimension: {expected}"

    def test_has_all_top_level_keys(self):
        report = empty_report("/tmp/foo")
        required = {
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
        }
        assert set(report.keys()) == required


class TestValidation:
    def test_valid_report_passes(self):
        report = _make_valid_report()
        errors = validate_report(report)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_report_strict_passes(self):
        report = _make_valid_report()
        validate_report_strict(report)  # Should not raise

    def test_missing_metadata(self):
        report = _make_valid_report()
        del report["metadata"]
        errors = validate_report(report)
        assert any("metadata" in e.lower() for e in errors)

    def test_invalid_confidence(self):
        report = _make_valid_report()
        report["purpose"]["confidence"] = "SUPER_HIGH"  # type: ignore
        errors = validate_report(report)
        assert any("purpose" in e and "confidence" in e for e in errors)

    def test_missing_dimension(self):
        report = _make_valid_report()
        report["dimensions"] = report["dimensions"][:10]  # Remove some
        errors = validate_report(report)
        assert any("missing dimension" in e for e in errors)

    def test_recommendation_without_evidence(self):
        report = _make_valid_report()
        report["recommendations"][0]["evidence"] = []
        errors = validate_report(report)
        assert any("evidence" in e for e in errors)

    def test_invalid_recommendation_category(self):
        report = _make_valid_report()
        report["recommendations"][0]["category"] = "NONSENSE"
        errors = validate_report(report)
        assert any("category" in e and "NONSENSE" in e for e in errors)

    def test_invalid_priority(self):
        report = _make_valid_report()
        report["recommendations"][0]["priority"] = "CRITICAL"
        errors = validate_report(report)
        assert any("priority" in e for e in errors)

    def test_invalid_tier(self):
        report = _make_valid_report()
        report["metadata"]["analysis_tier"] = "SUPER_DEEP"
        errors = validate_report(report)
        assert any("tier" in e.lower() for e in errors)


class TestValidationError:
    def test_raises_on_invalid(self):
        report = _make_valid_report()
        report["metadata"]["analysis_tier"] = "BAD"
        with pytest.raises(ValidationError):
            validate_report_strict(report)


class TestJSONSchema:
    def test_generates_valid_json(self):
        schema = generate_json_schema()
        # Verify it's parseable
        serialized = json.dumps(schema)
        parsed = json.loads(serialized)
        assert parsed["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert parsed["title"] == "Repo Oracle Report"

    def test_defs_present(self):
        schema = generate_json_schema()
        assert "$defs" in schema
        assert "finding" in schema["$defs"]
        assert "evidence_source" in schema["$defs"]
        assert "recommendation" in schema["$defs"]


class TestConvenienceFunctions:
    def test_new_finding_defaults(self):
        f = new_finding("test_dim")
        assert f["dimension"] == "test_dim"
        assert f["confidence"] == "UNKNOWN"
        assert f["evidence"] == []

    def test_new_evidence(self):
        e = new_evidence("file:test.py:1", "file", "Test file")
        assert e["id"] == "file:test.py:1"
        assert e["type"] == "file"

    def test_new_recommendation(self):
        r = new_recommendation("r1", "DOCUMENT", "LOW", "Add docs", "Needs docs")
        assert r["id"] == "r1"
        assert r["category"] == "DOCUMENT"
        assert r["priority"] == "LOW"
        assert r["estimated_effort"] == "MEDIUM"  # default
