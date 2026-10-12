# WordStream

WordStream (单词流) is a mobile-first words and fixed phrases read-along PWA
built as a modular FastAPI monolith.

The repository is at Stage 1: application shell, SQLite migrations, settings,
single-user security, and vocabulary import and browsing. Imports support
pasted text, CSV, TSV, TXT, JSON, and manual entry with a preview-before-commit
workflow.

## Architecture

HTTP APIs and Jinja2 web routes call services. Services own transaction
boundaries through a Unit of Work; repositories may query, add, and flush but
never commit. SQLAlchemy models are migrated exclusively through Alembic.

See [architecture](docs/architecture.md), [ADRs](docs/adr/), and the
[later-stage planning baseline](docs/planning/stage-1-api-contract.md).

## Requirements

- Python 3.11+
- `curl` for installing the pinned Tailwind standalone CLI

No Node.js installation or frontend package manager is required.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env
./scripts/build_css.sh
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`. The API health endpoint is
`http://127.0.0.1:8000/api/v1/health`.

Local development defaults to `AUTH_MODE=disabled`. To exercise the password
gate, set `AUTH_MODE=password`, `APP_PASSWORD`, and `SECRET_KEY`.

## Checks

```bash
ruff check .
black --check .
mypy app
pytest
alembic check
pre-commit run --all-files
```

Pytest includes branch coverage and requires at least 80%. Install the Git
hooks with `pre-commit install`.

The import page is `http://127.0.0.1:8000/vocabularies/import`.

## Tailwind

`./scripts/build_css.sh` downloads Tailwind CSS standalone `v3.4.17` into the
ignored `.tools` directory when needed, then writes the committed
`app/web/static/css/app.css`.

## Deployment

Production deployment is intentionally left to a later stage. The minimum
contract is:

- run `alembic upgrade head` before serving traffic;
- set `ENVIRONMENT=production`, `AUTH_MODE=password`, `APP_PASSWORD`, and
  `SECRET_KEY`;
- terminate HTTPS at the reverse proxy;
- persist and back up the SQLite `data` directory;
- run one application process unless SQLite write behavior has been reviewed.

Production startup rejects missing password or signing-key configuration.

## Stage 1 acceptance

```bash
alembic upgrade head
pytest
uvicorn app.main:app
curl http://127.0.0.1:8000/api/v1/health
```

The health response must report database status `ok` and migration status
`current`.
