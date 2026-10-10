# ADR 002: Alembic from the initial schema

Status: Accepted

All persistent schema changes use Alembic. Runtime startup does not call
`create_all`.

CI verifies upgrades. Because SQLite has limited `ALTER TABLE` support,
production rollback uses backups or forward fixes; destructive downgrade
support is not presented as a guarantee.
