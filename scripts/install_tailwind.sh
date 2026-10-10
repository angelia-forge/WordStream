#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${ROOT_DIR}/.tools"
TAILWIND_VERSION="${TAILWIND_VERSION:-v3.4.17}"
TAILWIND_BIN="${TAILWIND_BIN:-${TOOLS_DIR}/tailwindcss}"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) asset="tailwindcss-macos-arm64" ;;
  Darwin-x86_64) asset="tailwindcss-macos-x64" ;;
  Linux-aarch64 | Linux-arm64) asset="tailwindcss-linux-arm64" ;;
  Linux-x86_64) asset="tailwindcss-linux-x64" ;;
  *)
    echo "Unsupported platform: $(uname -s) $(uname -m)" >&2
    exit 1
    ;;
esac

mkdir -p "${TOOLS_DIR}"
curl --fail --location --silent --show-error \
  "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${asset}" \
  --output "${TAILWIND_BIN}"
chmod +x "${TAILWIND_BIN}"
"${TAILWIND_BIN}" --help >/dev/null
echo "Installed Tailwind CSS ${TAILWIND_VERSION} at ${TAILWIND_BIN}"
