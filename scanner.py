#!/usr/bin/env python3
"""Repo Oracle — Deterministic Repository Scanner.

Produces a reproducible JSON snapshot of a local repository:
languages, build system, git status, file inventory, and structural overview.
READ-ONLY: never modifies the target repo. Secret files detected by name only.

Usage:
    python3 scanner.py --repo /path/to/repo [--output scan.json] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Constants ───────────────────────────────────────────────────────────────

# Directories to skip entirely (never entered)
EXCLUDED_DIRS: set[str] = {
    ".git", "node_modules", ".venv", "venv", "vendor",
    "__pycache__", ".tox", ".eggs", "build", "dist",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", ".nuxt", ".output", "target",  # Rust/Cargo build
}

# Files to skip for content analysis (but noted in inventory)
EXCLUDED_CONTENT_PATTERNS: list[str] = [
    r"\.pyc$", r"\.pyo$", r"\.o$", r"\.so$", r"\.dylib$",
    r"\.exe$", r"\.dll$", r"\.bin$", r"\.dat$", r"\.zip$",
    r"\.tar$", r"\.gz$", r"\.7z$", r"\.rar$", r"\.jpg$",
    r"\.jpeg$", r"\.png$", r"\.gif$", r"\.ico$", r"\.svg$",
    r"\.mp3$", r"\.mp4$", r"\.wav$", r"\.webm$",
    r"\.ttf$", r"\.woff2?$", r"\.eot$",
    r"\.pdf$", r"\.docx?$", r"\.xlsx?$",
    r"\.DS_Store$", r"\.lock$",
]

# Files that indicate SECRETS — detected by name, NEVER read
SECRET_PATTERNS: list[str] = [
    r"\.env$", r"\.env\..*", r"credentials", r"\.pem$", r"\.key$",
    r"id_rsa", r"id_ed25519", r"id_ecdsa", r"\.pfx$", r"\.p12$",
    r"secrets?\..*", r"\.htpasswd$", r"\.netrc$",
]

MAX_FILE_SIZE_BYTES = 1_000_000  # 1MB — skip content for larger files
MAX_SCAN_FILES = 10_000          # Hard cap on files scanned
MAX_DEPTH_STRUCTURAL = 4         # Max depth for structural overview
SCANNER_TIMEOUT = 60             # Seconds

# ── Language Detection ──────────────────────────────────────────────────────

EXTENSION_MAP: dict[str, str] = {
    ".py": "Python", ".pyi": "Python", ".pyx": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".rs": "Rust", ".rlib": "Rust",
    ".go": "Go",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cxx": "C++",
    ".cs": "C#",
    ".rb": "Ruby", ".rake": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala", ".sc": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".svg": "SVG",
    ".md": "Markdown", ".mdx": "Markdown", ".rst": "reStructuredText",
    ".sql": "SQL",
    ".lua": "Lua",
    ".r": "R", ".R": "R",
    ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang",
    ".hs": "Haskell",
    ".clj": "Clojure", ".cljs": "ClojureScript", ".edn": "Clojure",
    ".elm": "Elm",
    ".zig": "Zig",
    ".nim": "Nim",
    ".tf": "Terraform", ".tfvars": "Terraform",
    ".proto": "Protobuf",
    ".graphql": "GraphQL", ".gql": "GraphQL",
    ".vue": "Vue", ".svelte": "Svelte",
    ".dockerfile": "Dockerfile",
    ".gradient": "Gradient", ".gr": "Gradient",
}

# ── Build System Detection ──────────────────────────────────────────────────

BUILD_SYSTEM_FILES: dict[str, str] = {
    "pyproject.toml": "Python (setuptools/poetry/hatch)",
    "setup.py": "Python (setuptools)",
    "setup.cfg": "Python (setuptools)",
    "requirements.txt": "Python (pip)",
    "Pipfile": "Python (pipenv)",
    "poetry.lock": "Python (poetry)",
    "package.json": "Node.js (npm/yarn)",
    "yarn.lock": "Node.js (yarn)",
    "pnpm-lock.yaml": "Node.js (pnpm)",
    "package-lock.json": "Node.js (npm)",
    "Cargo.toml": "Rust (cargo)",
    "Cargo.lock": "Rust (cargo)",
    "go.mod": "Go (modules)",
    "go.sum": "Go (modules)",
    "Makefile": "Make",
    "CMakeLists.txt": "CMake",
    "meson.build": "Meson",
    "BUILD": "Bazel",
    "WORKSPACE": "Bazel",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "build.gradle.kts": "Java (Gradle Kotlin DSL)",
    "settings.gradle": "Java (Gradle)",
    "Gemfile": "Ruby (Bundler)",
    "Rakefile": "Ruby (Rake)",
    "composer.json": "PHP (Composer)",
    "CMakeCache.txt": "CMake",
    "configure.ac": "Autotools",
    "configure": "Autotools",
    "SConstruct": "SCons",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    ".github/workflows/": "GitHub Actions",
    ".gitlab-ci.yml": "GitLab CI",
    "Jenkinsfile": "Jenkins",
}

TEST_FRAMEWORK_PATTERNS: dict[str, str] = {
    "pytest": "pytest",
    "jest.config": "Jest",
    "vitest.config": "Vitest",
    "karma.conf": "Karma",
    "mocha.opts": "Mocha",
    ".mocharc": "Mocha",
    "phpunit.xml": "PHPUnit",
    "rspec": "RSpec",
    "Cargo.toml": "cargo test",   # Only if [dev-dependencies] has test deps
}

ENTRYPOINT_PATTERNS: list[str] = [
    "main.py", "app.py", "index.py", "run.py", "server.py", "manage.py",
    "main.js", "index.js", "app.js", "server.js",
    "main.ts", "index.ts", "app.ts",
    "main.rs", "lib.rs",
    "main.go",
    "Main.java", "Application.java",
    "Program.cs",
    "index.html",
]

DOCUMENTATION_FILES: set[str] = {
    "README.md", "README", "README.rst", "README.txt",
    "CONTRIBUTING.md", "CONTRIBUTING.rst",
    "CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md",
    "LICENSE", "LICENSE.md", "LICENSE.txt",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "ARCHITECTURE.md", "ARCHITECTURE.txt",
    "docs/", "doc/", "documentation/",
}

CI_CD_FILES: set[str] = {
    ".github/workflows", ".github/actions",
    ".gitlab-ci.yml", ".gitlab-ci.yaml",
    "Jenkinsfile", "jenkinsfile",
    ".circleci/config.yml",
    ".travis.yml",
    ".drone.yml",
    "azure-pipelines.yml",
    ".buildkite/",
    "bitbucket-pipelines.yml",
}

DOCKER_FILES: set[str] = {
    "Dockerfile", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    "Dockerfile.prod", "Dockerfile.dev",
    ".dockerignore",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_excluded_dir(dirname: str) -> bool:
    return dirname in EXCLUDED_DIRS or dirname.startswith(".") and dirname not in (
        ".github", ".gitlab", ".circleci", ".vscode", ".devcontainer",
        ".cursor", ".hermes",
    )


def _is_content_excluded(filename: str) -> bool:
    for pat in EXCLUDED_CONTENT_PATTERNS:
        if re.search(pat, filename, re.IGNORECASE):
            return True
    return False


def _is_secret(filename: str) -> bool:
    for pat in SECRET_PATTERNS:
        if re.search(pat, filename, re.IGNORECASE):
            return True
    return False


def _slugify(name: str) -> str:
    """Convert a repo name to a safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


def _run_git(repo_path: str, *args: str) -> tuple[int, str, str]:
    """Run a git command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return 1, "", str(e)


def _has_git(repo_path: str) -> bool:
    """Check if the directory is a git repository."""
    return Path(repo_path, ".git").is_dir()


# ── Main Scanner ────────────────────────────────────────────────────────────

def scan_repo(repo_path: str) -> dict:
    """Run the full deterministic scan and return a ScannerOutput-compatible dict."""
    start_time = time.time()
    repo_path = os.path.abspath(repo_path)

    if not os.path.isdir(repo_path):
        return _error_output(repo_path, f"Not a directory: {repo_path}")

    repo_name = os.path.basename(repo_path)
    repo_slug = _slugify(repo_name)
    has_git = _has_git(repo_path)

    # ── Git metadata ──
    git_info = _collect_git_info(repo_path, has_git)

    # ── File inventory ──
    file_data = _walk_repo(repo_path)

    # ── Build systems & test frameworks ──
    build_systems = _detect_build_systems(file_data["all_files"])
    test_frameworks = _detect_test_frameworks(file_data["all_files"], build_systems)
    entrypoints = _detect_entrypoints(file_data["all_files"])

    # ── Special files ──
    dep_files = [f for f in file_data["all_files"]
                 if os.path.basename(f) in {
                     "package.json", "pyproject.toml", "Cargo.toml",
                     "go.mod", "Gemfile", "composer.json", "pom.xml",
                     "build.gradle", "build.gradle.kts",
                 }]
    ci_cd = [f for f in file_data["all_files"]
             if any(f.startswith(os.path.join(repo_path, c)) or
                    os.path.basename(f) in CI_CD_FILES
                    for c in CI_CD_FILES)]
    docker = [f for f in file_data["all_files"]
              if os.path.basename(f) in DOCKER_FILES]
    docs = [f for f in file_data["all_files"]
            if os.path.basename(f) in DOCUMENTATION_FILES or
               "docs/" in f.replace(repo_path + "/", "") or
               "doc/" in f.replace(repo_path + "/", "")]

    # ── Monorepo signal ──
    monorepo = _detect_monorepo(file_data["all_files"], repo_path)

    # ── Top-level directories ──
    top_dirs = _top_level_dirs(repo_path)

    # ── GitNexus integration (optional) ──
    gitnexus_data = _collect_gitnexus_data(repo_path)

    duration = time.time() - start_time

    output = {
        "repo_path": repo_path,
        "repo_name": repo_name,
        "repo_slug": repo_slug,
        "has_git": has_git,
        "has_gitnexus": gitnexus_data["has_gitnexus"],
        "gitnexus_symbols": gitnexus_data["symbol_count"],
        "gitnexus_flows": gitnexus_data["flow_count"],
        "gitnexus_top_symbols": gitnexus_data["top_symbols"],
        "git_branch": git_info["branch"],
        "git_remote": git_info["remote"],
        "last_commit_date": git_info["last_commit_date"],
        "last_commit_hash": git_info["last_commit_hash"],
        "commit_count": git_info["commit_count"],
        "contributors": git_info["contributors"],
        "dirty": git_info["dirty"],
        "untracked_count": git_info["untracked_count"],
        "modified_count": git_info["modified_count"],
        "staged_count": git_info["staged_count"],
        "languages": file_data["languages"],
        "build_systems": build_systems,
        "test_frameworks": test_frameworks,
        "entrypoints": entrypoints,
        "total_files": file_data["total_files"],
        "total_dirs": file_data["total_dirs"],
        "total_size_bytes": file_data["total_size_bytes"],
        "excluded_count": file_data["excluded_count"],
        "secret_files_detected": file_data["secret_files"],
        "monorepo_signal": monorepo,
        "top_level_dirs": top_dirs,
        "dependency_files": [os.path.relpath(f, repo_path) for f in dep_files],
        "ci_cd_files": [os.path.relpath(f, repo_path) for f in ci_cd],
        "docker_files": [os.path.relpath(f, repo_path) for f in docker],
        "documentation_files": [os.path.relpath(f, repo_path) for f in docs],
        "scan_duration_seconds": round(duration, 3),
        "error": None,
    }

    return output


def _collect_git_info(repo_path: str, has_git: bool) -> dict:
    if not has_git:
        return {
            "branch": "", "remote": "", "last_commit_date": "",
            "last_commit_hash": "", "commit_count": 0,
            "contributors": [], "dirty": False,
            "untracked_count": 0, "modified_count": 0, "staged_count": 0,
        }

    # Branch
    _, branch, _ = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")

    # Remote
    _, remote, _ = _run_git(repo_path, "remote", "get-url", "origin")

    # Last commit
    _, last_hash, _ = _run_git(repo_path, "log", "-1", "--format=%H")
    _, last_date, _ = _run_git(repo_path, "log", "-1", "--format=%aI")

    # Commit count
    _, count_str, _ = _run_git(repo_path, "rev-list", "--count", "HEAD")
    commit_count = int(count_str) if count_str.isdigit() else 0

    # Contributors
    _, contribs, _ = _run_git(repo_path, "shortlog", "-sne", "HEAD")
    contributors = []
    if contribs:
        for line in contribs.split("\n")[:20]:  # Cap at 20
            parts = line.strip().split("\t", 1)
            if len(parts) == 2:
                contributors.append(parts[1].strip())

    # Status
    dirty = False
    untracked, modified, staged = 0, 0, 0
    _, status_out, _ = _run_git(repo_path, "status", "--porcelain")
    if status_out:
        dirty = True
        for line in status_out.split("\n"):
            if not line.strip():
                continue
            idx = line[:2]
            if idx.strip() == "??":
                untracked += 1
            elif idx[0] in "MRC" and idx[1] != " ":
                staged += 1
            elif idx[1] in "MD":
                modified += 1

    return {
        "branch": branch,
        "remote": remote,
        "last_commit_date": last_date,
        "last_commit_hash": last_hash,
        "commit_count": commit_count,
        "contributors": contributors,
        "dirty": dirty,
        "untracked_count": untracked,
        "modified_count": modified,
        "staged_count": staged,
    }


def _walk_repo(repo_path: str) -> dict:
    """Walk the repo, collect language stats, file inventory, secret files."""
    languages: dict[str, int] = {}
    all_files: list[str] = []
    total_size = 0
    excluded_count = 0
    secret_files: list[str] = []
    total_dirs = 0

    try:
        for root, dirs, files in os.walk(repo_path):
            total_dirs += 1

            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            # Depth limit: don't go deeper than MAX_DEPTH_STRUCTURAL + 2 from root
            depth = root.replace(repo_path, "").count(os.sep)
            if depth > MAX_DEPTH_STRUCTURAL + 2:
                dirs[:] = []  # Stop recursion
                continue

            for filename in files:
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, repo_path)

                # Hard file cap
                if len(all_files) >= MAX_SCAN_FILES:
                    excluded_count += 1
                    continue

                all_files.append(filepath)

                # Detect secret files (name only, never read content)
                if _is_secret(filename):
                    secret_files.append(relpath)
                    excluded_count += 1
                    continue

                # Skip content-excluded files
                if _is_content_excluded(filename):
                    excluded_count += 1
                    continue

                # Skip large files
                try:
                    fsize = os.path.getsize(filepath)
                except OSError:
                    excluded_count += 1
                    continue

                if fsize > MAX_FILE_SIZE_BYTES:
                    excluded_count += 1
                    continue

                total_size += fsize

                # Language detection
                ext = os.path.splitext(filename)[1].lower()
                if ext in EXTENSION_MAP:
                    lang = EXTENSION_MAP[ext]
                    languages[lang] = languages.get(lang, 0) + 1

                # Special extension-less files
                if filename == "Dockerfile":
                    languages["Dockerfile"] = languages.get("Dockerfile", 0) + 1
                elif filename == "Makefile":
                    languages["Makefile"] = languages.get("Makefile", 0) + 1

    except (PermissionError, OSError):
        pass

    return {
        "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
        "total_files": len(all_files),
        "total_dirs": total_dirs,
        "total_size_bytes": total_size,
        "excluded_count": excluded_count,
        "secret_files": secret_files,
        "all_files": all_files,
    }


def _detect_build_systems(all_files: list[str]) -> list[str]:
    """Detect build systems from file presence."""
    found: set[str] = set()
    for f in all_files:
        basename = os.path.basename(f)
        if basename in BUILD_SYSTEM_FILES:
            found.add(BUILD_SYSTEM_FILES[basename])
        # Check for .github/workflows/ as a directory indicator
        if "/.github/workflows/" in f.replace(os.sep, "/"):
            found.add("GitHub Actions")
    return sorted(found)


def _detect_test_frameworks(all_files: list[str], build_systems: list[str]) -> list[str]:
    """Detect test frameworks."""
    found: set[str] = set()
    for f in all_files:
        basename = os.path.basename(f)
        if basename == "pytest.ini" or basename == "pyproject.toml" and "pytest" in build_systems:
            found.add("pytest")
        if basename.startswith("jest.config"):
            found.add("Jest")
        if basename.startswith("vitest.config"):
            found.add("Vitest")
        if "test" in os.path.dirname(f).lower().split(os.sep)[-1]:
            found.add("test-directory-detected")
        if basename.startswith("test_") or basename.endswith("_test.py"):
            found.add("pytest")
        if basename.endswith(".test.js") or basename.endswith(".test.ts"):
            found.add("Jest/Vitest")
        if basename.endswith("_test.rs") or basename == "test.rs":
            found.add("cargo test")
        if basename.endswith("_test.go"):
            found.add("go test")
        if basename == "phpunit.xml" or basename == "phpunit.xml.dist":
            found.add("PHPUnit")
        if basename == "spec" or basename.endswith("_spec.rb"):
            found.add("RSpec")
    return sorted(found)


def _detect_entrypoints(all_files: list[str]) -> list[str]:
    """Detect likely entrypoints."""
    found: list[str] = []
    for f in all_files:
        basename = os.path.basename(f)
        if basename in ENTRYPOINT_PATTERNS:
            found.append(os.path.basename(f))
    return sorted(set(found))


def _detect_monorepo(all_files: list[str], repo_path: str) -> bool:
    """Detect monorepo signals — multiple package managers at different levels."""
    signals = 0
    seen_dirs: set[str] = set()
    for f in all_files:
        basename = os.path.basename(f)
        if basename in ("package.json", "Cargo.toml", "pyproject.toml", "go.mod", "pom.xml"):
            parent = os.path.dirname(os.path.relpath(f, repo_path))
            if parent != "." and parent not in seen_dirs:
                seen_dirs.add(parent)
                signals += 1
    return signals >= 2


def _top_level_dirs(repo_path: str) -> list[str]:
    """List top-level directories (excluding hidden/excluded)."""
    try:
        return sorted([
            d for d in os.listdir(repo_path)
            if os.path.isdir(os.path.join(repo_path, d)) and not d.startswith(".")
        ])
    except (PermissionError, OSError):
        return []


def _collect_gitnexus_data(repo_path: str) -> dict:
    """Check for GitNexus index and collect symbol/flow stats.
    
    Returns dict with has_gitnexus, symbol_count, flow_count, top_symbols.
    Gracefully handles missing gitnexus CLI or stale indices.
    """
    result: dict = {
        "has_gitnexus": False,
        "symbol_count": 0,
        "flow_count": 0,
        "top_symbols": [],
    }

    # Check if .gitnexus directory exists
    gitnexus_dir = Path(repo_path, ".gitnexus")
    if not gitnexus_dir.is_dir():
        return result

    # Check for meta.json for stats
    meta_path = gitnexus_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text())
            stats = meta.get("stats", {})
            result["has_gitnexus"] = True
            result["symbol_count"] = stats.get("symbols", 0)
            result["flow_count"] = stats.get("flows", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # Try running gitnexus query to get top symbols (best-effort)
    try:
        proc = subprocess.run(
            ["gitnexus", "query", "--repo", Path(repo_path).name, "main entry", "--limit", "10"],
            capture_output=True, text=True, timeout=15,
            cwd=repo_path,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # Parse symbol names from output (best-effort)
            lines = proc.stdout.strip().split("\n")
            for line in lines[:10]:
                # Extract symbol-like text
                stripped = line.strip()
                if stripped and not stripped.startswith("[") and len(stripped) < 120:
                    result["top_symbols"].append(stripped)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # gitnexus CLI not available or timed out

    return result


def _error_output(repo_path: str, message: str) -> dict:
    return {
        "repo_path": repo_path,
        "repo_name": os.path.basename(repo_path),
        "repo_slug": _slugify(os.path.basename(repo_path)),
        "has_git": False,
        "has_gitnexus": False,
        "gitnexus_symbols": 0,
        "gitnexus_flows": 0,
        "gitnexus_top_symbols": [],
        "git_branch": "", "git_remote": "", "last_commit_date": "",
        "last_commit_hash": "", "commit_count": 0, "contributors": [],
        "dirty": False, "untracked_count": 0, "modified_count": 0, "staged_count": 0,
        "languages": {}, "build_systems": [], "test_frameworks": [],
        "entrypoints": [], "total_files": 0, "total_dirs": 0,
        "total_size_bytes": 0, "excluded_count": 0, "secret_files_detected": [],
        "monorepo_signal": False, "top_level_dirs": [],
        "dependency_files": [], "ci_cd_files": [], "docker_files": [],
        "documentation_files": [], "scan_duration_seconds": 0.0,
        "error": message,
    }


# ── CLI Entry Point ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repo Oracle Scanner — deterministic repository analysis",
    )
    parser.add_argument("--repo", required=True, help="Path to repository to scan")
    parser.add_argument("--output", "-o", help="Output JSON file path (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    result = scan_repo(args.repo)
    json_str = json.dumps(result, indent=2 if args.json else None, ensure_ascii=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(json_str)
            f.write("\n")
        print(f"Scanner output written to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
