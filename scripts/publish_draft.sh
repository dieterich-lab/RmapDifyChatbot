#!/usr/bin/env bash
# Publish the current Dify draft to make it the live version.
# Usage: publish_draft.sh [--auto-login]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AUTO_LOGIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto-login) AUTO_LOGIN=1; shift ;;
    *) echo "Unknown argument: $1"; echo "Usage: $0 [--auto-login]"; exit 1 ;;
  esac
done

ENV_FILE="$REPO_ROOT/.env"
SESSION_FILE="$REPO_ROOT/.secrets/dify_console_session.env"

[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
: "${DIFY_APP_ID:?DIFY_APP_ID is required}"

if [[ "$AUTO_LOGIN" == "1" ]]; then
  : "${DIFY_CONSOLE_EMAIL:?DIFY_CONSOLE_EMAIL is required}"
  : "${DIFY_CONSOLE_PASSWORD_B64:?DIFY_CONSOLE_PASSWORD_B64 or DIFY_CONSOLE_PASSWORD is required}"
  echo "Refreshing console session..."
  "$SCRIPT_DIR/import_dify_dsl.sh" /dev/null --auto-login 2>/dev/null || true
  [[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
fi

: "${DIFY_CONSOLE_COOKIE:?No session. Use --auto-login or set DIFY_CONSOLE_COOKIE.}"
: "${DIFY_CSRF_TOKEN:?No CSRF token. Use --auto-login or set DIFY_CSRF_TOKEN.}"

PUBLISH_URL="${DIFY_BASE_URL%/}/console/api/apps/${DIFY_APP_ID}/workflows/publish"

echo "Publishing draft of app ${DIFY_APP_ID}..."
HTTP=$(curl -sS -w "%{http_code}" -o /tmp/publish_result.txt -X POST "$PUBLISH_URL" \
  -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
  -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{}')

if [[ "$HTTP" == "200" ]]; then
  echo "✅ Published successfully!"
  cat /tmp/publish_result.txt
else
  echo "❌ Publish failed (HTTP $HTTP):"
  cat /tmp/publish_result.txt
  exit 1
fi
