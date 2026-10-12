# WordStream Architecture

## Scope

WordStream is a mobile-first FastAPI application with SQLite, server-rendered
pages, migrations, request tracing, and a single-user security boundary.
Vocabulary import and management use the same layered application structure as
the settings foundation.

## Layers

- `api`: HTTP validation, authentication, status codes, and response schemas.
- `web`: Jinja2 pages and static PWA shell resources.
- `services`: use cases and transaction boundaries.
- `repositories`: persistence operations without transaction ownership.
- `models`: SQLAlchemy persistence models.
- `schemas`: Pydantic request and response models.
- `utils`: framework-light shared helpers.

Dependencies point inward from API and web routes to services, then to Unit of
Work and repositories. Repositories may query, add, and flush, but must not
commit or roll back. A service commits a complete use case; an exception
causes rollback when the Unit of Work exits.

## Runtime flow

1. Session and request-ID middleware process the incoming request.
2. API or web routes validate input and invoke a service.
3. The service opens a Unit of Work.
4. Repositories operate on the Unit of Work session.
5. The service commits, or the Unit of Work rolls back on failure.
6. Errors use the common response envelope and include the request ID.

## Data evolution

Alembic owns all schema changes. Application startup never calls
`create_all`. CI and integration tests verify that an empty SQLite database can
upgrade to `head` and that model metadata has no pending migration operations.

## Vocabulary deletion

Vocabulary deletion is one service-owned Unit of Work transaction. Database
foreign keys cascade deletion to entries, study plans, and review states.
Learning events are retained with `entry_id` set to null and contain immutable
term, vocabulary, timezone, and activity-date snapshots. Historical statistics
read only those snapshots, so deleting active study data does not alter totals
or streaks. See [ADR 004](adr/004-history-retention.md).

## Security boundary

Local development may explicitly disable authentication. Production requires a
shared password and session signing key. Browser sessions use signed,
HTTP-only cookies and CSRF protection for writes. Secrets and imported content
must never be logged.

## Frontend boundary

Jinja2 renders the application shell. HTMX and Alpine.js are available for
later progressive enhancement. Tailwind CSS is compiled with its pinned
standalone CLI; no Node package or frontend bundler is required. The service
worker caches static shell assets only and does not claim offline learning.

## Observability

Request middleware accepts a valid UUIDv4 `X-Request-ID` or generates one. The
same value is returned in the response header, attached to structured standard
library logs, and included in structured errors.
