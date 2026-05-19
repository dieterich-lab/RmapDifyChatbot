#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 --app-id <app-id> --query <text> [--query <text> ...] [--classifier-node-id <id>] [--allow-cookie-auth]"
  exit 1
fi

APP_ID=""
CLASSIFIER_NODE_ID="1778150713944"
ALLOW_COOKIE_AUTH=0
declare -a QUERIES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --app-id"; exit 1; }
      APP_ID="$1"
      shift
      ;;
    --query)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --query"; exit 1; }
      QUERIES+=("$1")
      shift
      ;;
    --classifier-node-id)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --classifier-node-id"; exit 1; }
      CLASSIFIER_NODE_ID="$1"
      shift
      ;;
    --allow-cookie-auth)
      ALLOW_COOKIE_AUTH=1
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 --app-id <app-id> --query <text> [--query <text> ...] [--classifier-node-id <id>] [--allow-cookie-auth]"
      exit 1
      ;;
  esac
done

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
[[ -n "$APP_ID" ]] || { echo "--app-id is required"; exit 1; }
[[ ${#QUERIES[@]} -gt 0 ]] || { echo "At least one --query is required"; exit 1; }

# Guardrail: app runtime keys (usually prefix app-) do not authorize console endpoints.
if [[ -n "${DIFY_API_KEY:-}" && -z "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  echo "Detected DIFY_API_KEY but missing DIFY_CONSOLE_API_KEY."
  echo "For draft console endpoints (/console/api), use DIFY_CONSOLE_API_KEY or --allow-cookie-auth with DIFY_CONSOLE_COOKIE + DIFY_CSRF_TOKEN."
  exit 1
fi

BASE_URL="${DIFY_BASE_URL%/}"
RUN_URL="$BASE_URL/console/api/apps/$APP_ID/advanced-chat/workflows/draft/run"

auth_mode=""
declare -a AUTH_HEADERS=()
if [[ -n "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  auth_mode="api-key"
  AUTH_HEADERS=(-H "Authorization: Bearer ${DIFY_CONSOLE_API_KEY}")
else
  [[ "$ALLOW_COOKIE_AUTH" == "1" ]] || {
    echo "DIFY_CONSOLE_API_KEY is required."
    echo "If you explicitly want cookie auth, re-run with --allow-cookie-auth and provide DIFY_CONSOLE_COOKIE/DIFY_CSRF_TOKEN."
    exit 1
  }
  : "${DIFY_CONSOLE_COOKIE:?DIFY_CONSOLE_COOKIE is required with --allow-cookie-auth}"
  : "${DIFY_CSRF_TOKEN:?DIFY_CSRF_TOKEN is required with --allow-cookie-auth}"
  auth_mode="cookie-fallback"
  AUTH_HEADERS=(-H "Cookie: ${DIFY_CONSOLE_COOKIE}" -H "x-csrf-token: ${DIFY_CSRF_TOKEN}")
fi

echo "Run endpoint: $RUN_URL"
echo "Auth mode: $auth_mode"

for q in "${QUERIES[@]}"; do
  echo ""
  echo "=== Query ==="
  echo "$q"

  payload=$(jq -cn --arg q "$q" '{query:$q, inputs:{}, files:[], response_mode:"streaming", user:"route-debug-script"}')
  tmp_out=$(mktemp)
  http_code=$(curl -sS -o "$tmp_out" -w "%{http_code}" -X POST "$RUN_URL" \
    "${AUTH_HEADERS[@]}" \
    -H "Content-Type: application/json" \
    --data "$payload")

  echo "HTTP: $http_code"
  if [[ "$http_code" != "200" ]]; then
    cat "$tmp_out"
    continue
  fi

  class_name=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r --arg id "$CLASSIFIER_NODE_ID" 'select(.event=="node_finished" and .data.node_id==$id) | .data.outputs.class_name' | tail -n1)
  class_id=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r --arg id "$CLASSIFIER_NODE_ID" 'select(.event=="node_finished" and .data.node_id==$id) | .data.outputs.class_id' | tail -n1)
  answer=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r 'select(.event=="message") | .answer' | tr -d '\r' | paste -sd '' - | perl -0777 -pe 's/<think>.*?<\/think>//sg')

  echo "Classifier node: $CLASSIFIER_NODE_ID"
  echo "Class ID: ${class_id:-<none>}"
  echo "Class Name: ${class_name:-<none>}"
  echo "Answer preview:"
  printf '%s\n' "$answer" | sed -n '1,20p'
done
