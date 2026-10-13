# ADR 000: Project structure

Status: Accepted

WordStream separates HTTP APIs, server-rendered web routes, services,
repositories, persistence models, and schemas inside one `app` package.
Supporting utilities remain independent of FastAPI where practical.

Tests mirror ownership boundaries:

- `tests/unit` covers services, parsers, algorithms, and transaction primitives.
- `tests/repository` exercises repository SQL against migrated SQLite files.
- `tests/integration` covers HTTP, security, SQLite, and Alembic behavior.
- `tests/e2e` covers mobile browser workflows and Web Speech API boundaries.
- `tests/fixtures` stores reusable non-secret test inputs.

This layout keeps ownership and test scope explicit while retaining one
deployable application.
