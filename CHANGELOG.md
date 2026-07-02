# Changelog

All notable changes to repo-oracle will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Unreleased

### Added
- Deterministic repository scanner (languages, git, build systems, file inventory)
- 14-dimension analysis model with confidence ratings (HIGH/MEDIUM/LOW/UNKNOWN/N/A)
- Professional HTML report with sidebar navigation, collapsible sections, dark/light theme
- Machine-readable JSON report with evidence registry
- Markdown report format for GitHub issues and PRs
- Typer CLI with Rich terminal output (`scan`, `investigate`, `version`)
- URL cloning support (`repo-oracle https://github.com/user/repo`)
- Secret file detection by name (contents never read)
- Security invariants: read-only, no network, symlink safety, resource limits
- Cross-platform support (Linux, macOS, Windows)
- GitHub Actions CI (3 OS × 3 Python versions)
- PyPI trusted publishing workflow
- Pre-commit hooks (ruff)
- Hermes Agent skill integration

[0.1.0]: https://github.com/graydeon/repo-oracle/releases/tag/v0.1.0
