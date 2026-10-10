# ADR 001: Modular monolith

Status: Accepted

WordStream uses one FastAPI deployment and one SQLite database. API, web,
service, repository, model, and schema boundaries remain explicit inside the
repository.

This keeps local operation and demonstration simple while preserving testable
business boundaries. Microservices, queues, Redis, and background workers are
outside the MVP.
