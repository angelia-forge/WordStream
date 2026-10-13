# API Examples

The examples assume `BASE_URL=http://127.0.0.1:8000`. Production automation
should send the configured API key:

```bash
export BASE_URL=http://127.0.0.1:8000
export APP_API_KEY=replace-me
ws_curl() {
  curl --fail-with-body -H "X-API-Key: $APP_API_KEY" "$@"
}
```

For browser-style authentication, log in with a cookie jar and send the
returned CSRF token on writes:

```bash
csrf_token=$(
  curl --fail-with-body -c cookies.txt \
    -H 'Content-Type: application/json' \
    -d '{"password":"replace-me"}' \
    "$BASE_URL/api/v1/auth/login" |
  jq -r .csrf_token
)

curl --fail-with-body -b cookies.txt \
  -H "X-CSRF-Token: $csrf_token" \
  -H 'Content-Type: application/json' \
  -X PATCH -d '{"timezone":"Asia/Shanghai"}' \
  "$BASE_URL/api/v1/settings"
```

## Import a Vocabulary

Preview performs no writes. Confirmation must send the digest returned by the
preview for the same source text.

```bash
cat > /tmp/words.txt <<'EOF'
term|meaning|pos|example
focus|专注|noun|Focus on one task.
in order to|为了|phrase|Read in order to learn.
EOF

preview=$(
  ws_curl -X POST \
    -F 'name=Starter words' \
    -F 'text=</tmp/words.txt' \
    "$BASE_URL/api/v1/vocabularies/import/preview"
)
digest=$(printf '%s' "$preview" | jq -r .preview_digest)

ws_curl -X POST \
  -F 'name=Starter words' \
  -F 'text=</tmp/words.txt' \
  -F "preview_digest=$digest" \
  "$BASE_URL/api/v1/vocabularies/import"
```

The response includes `vocabulary_id`; use it in the following examples:

```bash
export VOCABULARY_ID=1
```

## Configure a Study Plan

```bash
ws_curl -X PUT \
  -H 'Content-Type: application/json' \
  -d '{
    "daily_new_count": 20,
    "daily_review_count": 20,
    "interval_seconds": 5,
    "is_random": false,
    "is_loop": false
  }' \
  "$BASE_URL/api/v1/vocabularies/$VOCABULARY_ID/plan"
```

## Create and Record a Study Session

```bash
session=$(
  ws_curl -X POST \
    -H 'Content-Type: application/json' \
    -d "{\"vocabulary_id\":$VOCABULARY_ID,\"resume_existing\":true}" \
    "$BASE_URL/api/v1/study-sessions"
)
session_id=$(printf '%s' "$session" | jq -r .session.id)
item_id=$(printf '%s' "$session" | jq -r .items[0].id)
```

Each `client_event_id` must be a stable UUID for retries. `occurred_at` must
include a timezone and be within 24 hours of server time.

```bash
client_event_id=$(python -c 'import uuid; print(uuid.uuid4())')
occurred_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

ws_curl -X POST \
  -H 'Content-Type: application/json' \
  -d "{
    \"outcomes\":[{
      \"session_item_id\":\"$item_id\",
      \"client_event_id\":\"$client_event_id\",
      \"result\":\"seen\",
      \"attempt_count\":1,
      \"occurred_at\":\"$occurred_at\"
    }]
  }" \
  "$BASE_URL/api/v1/study-sessions/$session_id/outcomes/batch"

ws_curl -X POST \
  "$BASE_URL/api/v1/study-sessions/$session_id/finish"
```

## Statistics and Settings

```bash
ws_curl "$BASE_URL/api/v1/statistics/today"
ws_curl "$BASE_URL/api/v1/reviews/today?vocabulary_id=$VOCABULARY_ID"
ws_curl "$BASE_URL/api/v1/settings"
```

## Delete a Vocabulary

Deletion requires a matching confirmation query parameter:

```bash
ws_curl -X DELETE \
  "$BASE_URL/api/v1/vocabularies/$VOCABULARY_ID?confirm_id=$VOCABULARY_ID"
```

Errors use a common envelope containing `error.code`, `error.message`, and the
request ID. The same request ID is returned in the `X-Request-ID` header.
