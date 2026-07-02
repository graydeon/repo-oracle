# repo-oracle

**Investigate any Git repository with one command.**

[![PyPI](https://img.shields.io/pypi/v/repo-oracle)](https://pypi.org/project/repo-oracle/)
[![Python](https://img.shields.io/pypi/pyversions/repo-oracle)](https://pypi.org/project/repo-oracle/)
[![License](https://img.shields.io/github/license/graydeon/repo-oracle)](LICENSE)
[![CI](https://github.com/graydeon/repo-oracle/actions/workflows/ci.yml/badge.svg)](https://github.com/graydeon/repo-oracle/actions/workflows/ci.yml)

`repo-oracle` scans any local Git repository and produces a professional, evidence-backed audit report. It answers three questions for every repo:

1. **What is this?** — purpose, language, architecture, dependencies
2. **What condition is it in?** — activity, staleness, security, documentation
3. **What should I do next?** — ranked, evidence-linked recommendations

**No API keys. No cloud. Fully offline. 100% read-only.**

## Quick Start

```bash
pipx install repo-oracle

# Investigate the current directory
repo-oracle

# Investigate a specific repo
repo-oracle ~/dev/old-project

# Investigate a GitHub repo (clones to temp, cleans up after)
repo-oracle https://github.com/user/repo

# Quick scan only
repo-oracle scan ~/dev/project

# Output JSON to stdout
repo-oracle --json | jq .metadata.repo_name
```

## What You Get

**Terminal output** — rich summary with vital signs and top recommendations.

**HTML report** — professional single-file report with:
- Sidebar navigation
- Collapsible analysis dimensions
- Language breakdown charts
- Dark/light theme toggle
- Responsive layout (mobile-friendly)
- No CDN dependencies — works offline forever

**JSON report** — machine-readable canonical data with evidence registry.

**Markdown report** — paste into GitHub issues, PRs, or discussions.

## Analysis Dimensions

`repo-oracle` assesses 14 core dimensions:

| Dimension | What it tells you |
|-----------|-------------------|
| Purpose | What does this repo do? |
| Languages & Frameworks | What tech stack? |
| Build & Test System | How is it built? |
| Entrypoints | Where does execution start? |
| Architecture | How is it structured? |
| Dependency Graph | What does it depend on? |
| Runtime Assumptions | OS, versions, services? |
| Stale Dependencies | Are deps outdated? |
| Git History | Activity timeline, contributors |
| Open TODOs | Known issues |
| Documentation | How well documented? |
| Test Coverage | Are there tests? |
| Security Surface | Any obvious risks? |
| Deployment Clues | Docker, CI/CD, hosting? |

Plus 3 meta-dimensions: activity signal, value assessment, and next-action recommendation.

Every finding is **evidence-linked** with an explicit confidence rating (HIGH · MEDIUM · LOW · UNKNOWN · N/A).

## Safety Guarantees

- **READ-ONLY** — never modifies the target repo
- **No secrets** — detects `.env` and credential files by name only, never reads them
- **No execution** — never runs code from the target repo
- **No network** — fully offline by default
- **No telemetry** — completely private
- **Symlink safe** — never follows symlinks outside the repo root

These invariants are tested in CI.

## Installation

```bash
# Recommended: isolated install via pipx
pipx install repo-oracle

# Or into an existing venv
pip install repo-oracle
```

Requires Python 3.11+. Works on Linux, macOS, and Windows.

## Programmatic API

```python
from repo_oracle import scan_repo, validate_report_strict, render_report

# Run the deterministic scanner
scan = scan_repo("/path/to/repo")

# Access scanner output
print(scan["languages"])      # {"Python": 42, "JavaScript": 12}
print(scan["build_systems"])  # ["Python (setuptools/poetry/hatch)"]
print(scan["commit_count"])   # 156

# Build a full report (see schema.py for the TypedDict definitions)
from repo_oracle import empty_report, new_recommendation, new_evidence
report = empty_report(scan["repo_path"], scan["repo_name"], scan["repo_slug"])
# ... populate dimensions, evidence, recommendations ...
validate_report_strict(report)

# Render HTML
html = render_report(report, "report.json")
with open("report.html", "w") as f:
    f.write(html)
```

## Hermes Integration

`repo-oracle` started as a Hermes Agent skill and ships with optional Hermes integration for **agentic deep investigation**. The standalone CLI handles deterministic scanning. When loaded as a Hermes skill (`/skill repo-oracle`), the agent dispatches parallel sub-agents to deeply investigate git history, dependency freshness, security surface, and documentation quality — producing a richer report than the CLI alone.

```bash
# Hermes CLI wrapper
repo-oracle ~/dev/stale-project   # uses repo-oracle skill internally
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and PR guidelines.

```bash
git clone https://github.com/graydeon/repo-oracle.git
cd repo-oracle
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
