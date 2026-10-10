# ADR 000: Project structure

Status: Accepted

WordStream separates HTTP APIs, server-rendered web routes, services,
repositories, persistence models, and schemas inside one `app` package.
Supporting utilities remain independent of FastAPI where practical.

Tests mirror ownership boundaries:

- `tests/unit` covers configuration and transaction primitives.
- `tests/integration` covers HTTP, SQLite, and Alembic behavior.
- `tests/e2e` is reserved for later browser workflows.
- `tests/fixtures` stores reusable non-secret test inputs.

This layout keeps Stage 0 small while providing stable locations for later
features. Business modules are intentionally absent until their stage begins.
