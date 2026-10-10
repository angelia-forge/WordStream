#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAILWIND_BIN="${TAILWIND_BIN:-${ROOT_DIR}/.tools/tailwindcss}"

if [[ ! -x "${TAILWIND_BIN}" ]]; then
  "${ROOT_DIR}/scripts/install_tailwind.sh"
fi

cd "${ROOT_DIR}"
"${TAILWIND_BIN}" \
  --content "./app/web/templates/**/*.html,./app/web/static/js/**/*.js" \
  --input "${ROOT_DIR}/app/web/static/css/input.css" \
  --output "${ROOT_DIR}/app/web/static/css/app.css" \
  --minify
