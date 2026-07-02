# Security Policy

## Safety Guarantees

repo-oracle is designed with safety as a hard invariant. These guarantees are tested in CI on every commit:

1. **READ-ONLY** — The scanner never creates, modifies, or deletes files in the target repository. It reads file metadata and text content only.

2. **NEVER READS SECRETS** — Files matching secret patterns (`.env`, `credentials`, `*.pem`, `*.key`, `id_rsa*`, etc.) are detected by filename only. Their contents are never read, stored, or displayed.

3. **NEVER EXECUTES TARGET CODE** — The scanner never imports, evaluates, or executes any code from the target repository. Subprocess calls are limited to `git` commands and the `gitnexus` CLI.

4. **FULLY OFFLINE BY DEFAULT** — The scanner makes zero network calls. Package registry checks (npm, PyPI, crates.io) require an explicit opt-in flag.

5. **NO TELEMETRY** — repo-oracle collects no usage data, sends no crash reports, and makes no update checks. It is fully private.

6. **SYMLINK SAFETY** — The scanner uses `os.walk(followlinks=False)` and never follows symlinks outside the repository root.

7. **RESOURCE LIMITS** — Maximum 10,000 files scanned per run. Files larger than 1MB are skipped for content analysis. Git subprocess calls have timeouts.

## Reporting a Vulnerability

If you discover a security vulnerability in repo-oracle, please report it privately by emailing **gray@repo-oracle.dev**. Do not open a public issue.

We aim to acknowledge reports within 48 hours and provide a fix within 7 days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ |

## Scope

The security guarantees apply to the standalone CLI (`repo-oracle`) and the Python API (`repo_oracle` package). The Hermes Agent integration inherits these guarantees and adds agentic analysis capabilities.
