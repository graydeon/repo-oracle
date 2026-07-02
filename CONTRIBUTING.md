# Contributing

Thanks for your interest in contributing to repo-oracle!

## Development Setup

```bash
git clone https://github.com/graydeon/repo-oracle.git
cd repo-oracle
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ -v
```

Coverage target: ≥85% line coverage. Enforced in CI.

## Code Style

- **Ruff** for linting and formatting (`ruff check src/ tests/ && ruff format src/ tests/`)
- **MyPy** for type checking (`mypy src/ --strict`)
- Pre-commit hooks are configured — run `pre-commit install` after cloning

## Pull Requests

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Run `python -m pytest tests/ -v` and ensure all pass
4. Run `ruff check src/ tests/ && ruff format --check src/ tests/`
5. Submit a PR with a clear description

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):
```
feat: add Markdown report format
fix: handle empty language dict in HTML template
chore: update dependencies
docs: add usage examples to README
```

## Project Structure

```
src/repo_oracle/        # Package source
  scanner.py            # Deterministic repository scanner
  schema.py             # Report schema (TypedDict) and validation
  render.py             # JSON → HTML + Markdown renderer
  writer.py             # Report file output
  cli.py                # Typer CLI entry point
  templates/            # Jinja2 templates
tests/                  # Test suite
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
