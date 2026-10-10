# WordStream

WordStream (单词流) is a mobile-first words and fixed phrases read-along PWA
built as a modular FastAPI monolith.

The repository is currently at **Stage 0**: application scaffold, Alembic,
settings, Unit of Work, request tracing, and a single-user security gate.

## Requirements

- Python 3.11+

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health`.

## Checks

```bash
pre-commit run --all-files
pytest
```

The pre-commit hooks run Ruff, Black, and mypy. The test command includes
branch coverage and requires at least 80%. Install the hooks locally with
`pre-commit install`.

## Documentation

- [Architecture](docs/architecture.md)
- [API contract](docs/api-contract.md)
- [Stage 0](docs/stage-0.md)

The PWA work planned for later stages will cache only the application shell.
WordStream does not currently claim offline learning support.
