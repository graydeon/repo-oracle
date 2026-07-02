"""Tests for repo-oracle writer module."""

import json
import os
import tempfile
from pathlib import Path

from repo_oracle.writer import (
    write_reports,
    _report_filename,
    _next_collision_suffix,
    _generate_repo_index,
    _generate_global_index,
)


class TestNaming:
    def test_report_filename(self):
        name = _report_filename("test-repo", "json")
        assert name.startswith("repo-oracle-test-repo-")
        assert name.endswith(".json")
        # Today's date should be in it
        from datetime import date

        assert date.today().isoformat() in name

    def test_report_filename_with_suffix(self):
        name = _report_filename("myrepo", "html", "-b")
        assert name.endswith("-b.html")
        assert ".html" in name

    def test_no_collision_on_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _next_collision_suffix(Path(tmpdir), "test", "json")
            assert result == ""

    def test_collision_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file that would collide
            import datetime

            today = datetime.date.today().isoformat()
            Path(tmpdir, f"repo-oracle-test-{today}.json").write_text("{}")
            result = _next_collision_suffix(Path(tmpdir), "test", "json")
            assert result == "-a"


class TestIndexGeneration:
    def test_repo_index_empty(self):
        html = _generate_repo_index(Path("/nonexistent"), "empty-repo")
        assert "empty-repo" in html
        assert "No reports yet" not in html  # It shows empty table

    def test_global_index_empty(self):
        html = _generate_global_index(Path("/nonexistent"))
        assert "Repo Oracle" in html
        assert "All Reports" in html


class TestWriteReports:
    def test_writes_to_temp_dir(self):
        """Test writing reports to a temp directory (no git)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy JSON and HTML reports
            json_path = Path(tmpdir, "test-report.json")
            html_path = Path(tmpdir, "test-report.html")
            json_path.write_text(
                json.dumps(
                    {
                        "metadata": {
                            "repo_name": "test-project",
                            "repo_slug": "test-project",
                        },
                        "executive_summary": "A test project.",
                    }
                ),
                encoding="utf-8",
            )
            html_path.write_text(
                "<!DOCTYPE html><html><body><h1>Test</h1></body></html>",
                encoding="utf-8",
            )

            # Create a fake context repo structure
            context_dir = Path(tmpdir, "context-repo")
            context_dir.mkdir()
            (context_dir / ".git").mkdir()  # Fake git dir

            result = write_reports(
                json_path=str(json_path),
                html_path=str(html_path),
                repo_slug="test-project",
                context_repo_path=str(context_dir),
                git_commit=False,
                git_push=False,
            )

            assert result["error"] is None
            assert result["repo_slug"] == "test-project"
            assert os.path.exists(result["saved_json"])
            assert os.path.exists(result["saved_html"])
            assert os.path.exists(result["repo_index"])
            assert os.path.exists(result["global_index"])

            # Verify index content
            index_html = Path(result["global_index"]).read_text()
            assert "test-project" in index_html

            repo_index = Path(result["repo_index"]).read_text()
            assert "test-project" in repo_index

    def test_files_have_correct_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir, "r.json")
            html_path = Path(tmpdir, "r.html")
            json_path.write_text("{}", encoding="utf-8")
            html_path.write_text("<html></html>", encoding="utf-8")

            context_dir = Path(tmpdir, "ctx")
            context_dir.mkdir()

            result = write_reports(
                json_path=str(json_path),
                html_path=str(html_path),
                repo_slug="my-cool-repo",
                context_repo_path=str(context_dir),
                git_commit=False,
                git_push=False,
            )

            json_name = os.path.basename(result["saved_json"])
            html_name = os.path.basename(result["saved_html"])
            assert json_name.startswith("repo-oracle-my-cool-repo-")
            assert html_name.startswith("repo-oracle-my-cool-repo-")
            assert json_name.endswith(".json")
            assert html_name.endswith(".html")

    def test_nonexistent_context_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir, "r.json")
            html_path = Path(tmpdir, "r.html")
            json_path.write_text("{}", encoding="utf-8")
            html_path.write_text("<html></html>", encoding="utf-8")

            # Context repo doesn't exist — should still create reports dir
            result = write_reports(
                json_path=str(json_path),
                html_path=str(html_path),
                repo_slug="test-slug",
                context_repo_path="/tmp/nonexistent-context-repo-99999",
                git_commit=False,
                git_push=False,
            )

            assert result["error"] is None
            assert os.path.exists(result["saved_json"])
