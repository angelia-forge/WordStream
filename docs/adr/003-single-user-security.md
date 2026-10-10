# ADR 003: Single-user security

Status: Accepted

WordStream uses one shared application password rather than user accounts.
Production startup requires both `APP_PASSWORD` and `SECRET_KEY`, and
authentication cannot be disabled in production.

Browser authentication uses a signed, HTTP-only, SameSite=Lax session cookie.
Production cookies are Secure. Cookie-authenticated writes require a CSRF
token, while optional API-key authentication is reserved for automation.

The shared password and signing key are environment secrets. They must not be
persisted in the database, committed to the repository, or written to logs.
