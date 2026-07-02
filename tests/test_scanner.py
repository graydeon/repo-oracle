"""Tests for repo-oracle scanner module."""

import json
import os
import tempfile
from pathlib import Path
import pytest
from repo_oracle.scanner import (
    scan_repo,
    _slugify,
    _is_excluded_dir,
    _is_content_excluded,
    _is_secret,
    _detect_build_systems,
    _detect_monorepo,
    _detect_entrypoints,
    EXCLUDED_DIRS,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("My Cool Repo") == "my-cool-repo"

    def test_special_chars(self):
        assert _slugify("foo@bar#baz!") == "foo-bar-baz"

    def test_empty(self):
        assert _slugify("") == "unknown"

    def test_only_special(self):
        assert _slugify("@#$%") == "unknown"


class TestExcludedDirs:
    def test_known_excluded(self):
        for d in ["node_modules", ".venv", "vendor", "__pycache__", ".git", "target"]:
            assert _is_excluded_dir(d), f"{d} should be excluded"

    def test_dot_dirs_allowed(self):
        for d in [".github", ".vscode", ".devcontainer", ".cursor"]:
            assert not _is_excluded_dir(d), f"{d} should NOT be excluded"


class TestContentExcluded:
    def test_binary(self):
        assert _is_content_excluded("foo.exe")
        assert _is_content_excluded("foo.o")
        assert _is_content_excluded("foo.so")

    def test_pyc(self):
        assert _is_content_excluded("module.pyc")

    def test_images(self):
        assert _is_content_excluded("photo.png")
        assert _is_content_excluded("photo.jpg")

    def test_source_not_excluded(self):
        assert not _is_content_excluded("main.py")
        assert not _is_content_excluded("app.js")
        assert not _is_content_excluded("lib.rs")


class TestSecretDetection:
    def test_env_files(self):
        assert _is_secret(".env")
        assert _is_secret(".env.local")
        assert _is_secret(".env.production")

    def test_key_files(self):
        assert _is_secret("id_rsa")
        assert _is_secret("id_ed25519")
        assert _is_secret("server.key")
        assert _is_secret("cert.pem")

    def test_credentials(self):
        assert _is_secret("credentials")
        assert _is_secret("credentials.json")

    def test_not_secret(self):
        assert not _is_secret("main.py")
        assert not _is_secret("README.md")
        assert not _is_secret("config.yaml")


class TestBuildSystemDetection:
    def test_python(self):
        files = ["/repo/pyproject.toml", "/repo/setup.py"]
        result = _detect_build_systems(files)
        assert any("setuptools" in r for r in result)

    def test_node(self):
        files = ["/repo/package.json"]
        result = _detect_build_systems(files)
        assert any("npm" in r for r in result)

    def test_rust(self):
        files = ["/repo/Cargo.toml"]
        result = _detect_build_systems(files)
        assert any("cargo" in r for r in result)

    def test_make(self):
        files = ["/repo/Makefile"]
        result = _detect_build_systems(files)
        assert "Make" in result


class TestMonorepoDetection:
    def test_not_monorepo(self):
        files = ["/repo/pyproject.toml", "/repo/src/main.py"]
        assert not _detect_monorepo(files, "/repo")

    def test_is_monorepo(self):
        files = [
            "/repo/frontend/package.json",
            "/repo/backend/pyproject.toml",
        ]
        assert _detect_monorepo(files, "/repo")

    def test_single_manager_at_root(self):
        files = ["/repo/package.json", "/repo/src/index.js"]
        assert not _detect_monorepo(files, "/repo")


class TestEntrypoints:
    def test_python(self):
        files = ["/repo/main.py", "/repo/src/utils.py"]
        result = _detect_entrypoints(files)
        assert "main.py" in result

    def test_js(self):
        files = ["/repo/index.js", "/repo/server.js"]
        result = _detect_entrypoints(files)
        assert "index.js" in result
        assert "server.js" in result


class TestScanRepo:
    """Integration tests using a temp directory."""

    def test_scan_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = scan_repo(tmpdir)
            assert result["repo_path"] == os.path.abspath(tmpdir)
            assert result["has_git"] is False
            assert result["total_files"] == 0
            assert result["error"] is None

    def test_scan_with_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            Path(tmpdir, "README.md").write_text("# Test Repo")
            Path(tmpdir, "main.py").write_text("print('hello')")
            Path(tmpdir, "pyproject.toml").write_text("[project]\nname='test'")
            Path(tmpdir, ".env").write_text("SECRET=xxx")  # Should be detected but never read

            result = scan_repo(tmpdir)

            assert result["total_files"] >= 3
            assert result["languages"]["Python"] >= 1
            assert result["languages"]["Markdown"] >= 1
            assert ".env" in result["secret_files_detected"]
            assert len(result["build_systems"]) >= 1
            assert not result["monorepo_signal"]

    def test_excluded_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node_modules = Path(tmpdir, "node_modules")
            node_modules.mkdir()
            Path(node_modules, "package.json").write_text("{}")

            result = scan_repo(tmpdir)
            # node_modules should be excluded entirely
            assert result["total_files"] == 0

    def test_scan_is_deterministic(self):
        """Same repo scanned twice should produce same output (modulo timing)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "main.py").write_text("print('hello')")
            Path(tmpdir, "lib.rs").write_text("fn main() {}")

            r1 = scan_repo(tmpdir)
            r2 = scan_repo(tmpdir)

            # Compare everything except scan_duration
            r1_copy = {k: v for k, v in r1.items() if k != "scan_duration_seconds"}
            r2_copy = {k: v for k, v in r2.items() if k != "scan_duration_seconds"}
            assert r1_copy == r2_copy

    def test_not_a_directory(self):
        result = scan_repo("/tmp/nonexistent-repo-99999")
        assert result["error"] is not None
        assert "Not a directory" in result["error"]

    def test_output_is_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "main.py").write_text("x = 1")
            result = scan_repo(tmpdir)
            # Verify we can serialize to JSON
            json_str = json.dumps(result)
            parsed = json.loads(json_str)
            assert parsed["repo_slug"] == _slugify(os.path.basename(tmpdir))
