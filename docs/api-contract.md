# Stage 0 API Contract

All application APIs use `/api/v1`. Errors have this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [],
    "request_id": "8ed0ad8a-9e0e-4fb6-a65e-53ffecb8e64d"
  }
}
```

## `GET /api/v1/health`

Public health check. It reports application, database, and migration status
without exposing database paths or credentials.

## `POST /api/v1/auth/login`

Accepts the shared application password and creates a signed, HTTP-only
session cookie. The response includes the CSRF token required by subsequent
cookie-authenticated write requests.

## `POST /api/v1/auth/logout`

Clears the session. Requires a valid CSRF token when cookie authentication is
enabled.

## `GET /api/v1/settings`

Returns the singleton application preferences.

## `PATCH /api/v1/settings`

Updates one or more preferences. The singleton uses primary key `id = 1` and a
database check constraint prevents other ids. Preferences are `timezone`,
`tts_rate`, `default_interval`, and `daily_goal`.

## Error codes

Stage 0 defines `VALIDATION_ERROR`, `UNAUTHORIZED`, `CSRF_FAILED`,
`RATE_LIMITED`, and `AUTH_DISABLED`.
