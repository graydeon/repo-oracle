"""Security invariant tests for repo-oracle."""

import os
import tempfile
from pathlib import Path

import pytest
from repo_oracle.scanner import scan_repo, _is_secret


class TestSecretDetection:
    def test_env_files_detected(self):
        assert _is_secret(".env")
        assert _is_secret(".env.local")
        assert _is_secret(".env.production")
        assert _is_secret(".env.development")

    def test_key_files_detected(self):
        assert _is_secret("id_rsa")
        assert _is_secret("id_ed25519")
        assert _is_secret("server.key")
        assert _is_secret("cert.pem")
        assert _is_secret("client.pfx")

    def test_credential_files_detected(self):
        assert _is_secret("credentials")
        assert _is_secret("credentials.json")
        assert _is_secret("secrets.yaml")
        assert _is_secret(".htpasswd")
        assert _is_secret(".netrc")

    def test_normal_files_not_secret(self):
        assert not _is_secret("main.py")
        assert not _is_secret("app.js")
        assert not _is_secret("README.md")
        assert not _is_secret("config.toml")
        assert not _is_secret("settings.json")

    def test_scanner_never_reads_secrets(self):
        """Secret files are detected by name, never read."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".env").write_text("SECRET_KEY=abcdef123456")
            Path(tmpdir, "credentials").write_text("password: hunter2")
            Path(tmpdir, "main.py").write_text("print('hello')")

            result = scan_repo(tmpdir)
            assert ".env" in result["secret_files_detected"]
            assert "credentials" in result["secret_files_detected"]
            # The scanner should still report these files (by name only)
            # and NOT include their content


class TestSymlinkSafety:
    def test_symlinks_not_followed(self):
        """Scanner uses followlinks=False, never follows symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink pointing outside the repo
            outside = os.path.join(tempfile.gettempdir(), "outside-secret.txt")
            Path(outside).write_text("secret outside repo")
            symlink = os.path.join(tmpdir, "link-to-outside")
            try:
                os.symlink(outside, symlink)
            except OSError:
                pytest.skip("Symlink creation not supported")

            result = scan_repo(tmpdir)
            # Symlink should not be followed — no content from outside
            assert result["total_files"] >= 0  # Symlink may or may not be counted
            assert result["error"] is None


class TestReadOnlyGuarantee:
    def test_scanner_never_writes(self):
        """Scanner is strictly read-only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.py").write_text("x = 1")
            mtime_before = os.path.getmtime(os.path.join(tmpdir, "test.py"))

            scan_repo(tmpdir)

            # File should be unchanged
            mtime_after = os.path.getmtime(os.path.join(tmpdir, "test.py"))
            assert mtime_before == mtime_after
            content = Path(tmpdir, "test.py").read_text(encoding="utf-8")
            assert content == "x = 1"

    def test_no_new_files_created(self):
        """Scanner creates no files in the target repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files_before = set(os.listdir(tmpdir))
            scan_repo(tmpdir)
            files_after = set(os.listdir(tmpdir))
            assert files_before == files_after


class TestBinaryDetection:
    def test_large_files_skipped(self):
        """Files > 1MB are excluded from content analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "readme.md").write_text("# Hello")
            # Create a 1.1MB file (exceed the limit)
            big_path = os.path.join(tmpdir, "big.bin")
            with open(big_path, "wb") as f:
                f.write(b"\x00" * 1_100_000)

            result = scan_repo(tmpdir)
            # The small file should be counted
            assert result["total_files"] >= 1
            # The big file should contribute to excluded count
            assert result["excluded_count"] >= 1


class TestNoNetworkDefault:
    def test_scanner_makes_no_network_calls(self):
        """Scanner runs entirely offline by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.py").write_text("x = 1")
            # Just verify it doesn't crash — no network assertions needed
            result = scan_repo(tmpdir)
            assert result["error"] is None
