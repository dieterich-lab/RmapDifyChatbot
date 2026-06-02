#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 --query <text> [--query <text> ...] [--user <id>] [--conversation-id <id>]"
  exit 1
fi

USER_ID="runtime-debug-script"
CONVERSATION_ID=""
declare -a QUERIES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --query)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --query"; exit 1; }
      QUERIES+=("$1")
      shift
      ;;
    --user)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --user"; exit 1; }
      USER_ID="$1"
      shift
      ;;
    --conversation-id)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --conversation-id"; exit 1; }
      CONVERSATION_ID="$1"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 --query <text> [--query <text> ...] [--user <id>] [--conversation-id <id>]"
      exit 1
      ;;
  esac
done

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"

# Preferred variable for runtime app endpoints is DIFY_APP_API_KEY (prefix app-).
APP_API_KEY="${DIFY_APP_API_KEY:-${DIFY_API_KEY:-}}"
: "${APP_API_KEY:?DIFY_APP_API_KEY (or fallback DIFY_API_KEY) is required}"
[[ "$APP_API_KEY" == app-* ]] || {
  echo "DIFY_APP_API_KEY must be an app key (prefix 'app-')."
  exit 1
}

[[ ${#QUERIES[@]} -gt 0 ]] || { echo "At least one --query is required"; exit 1; }

BASE_URL="${DIFY_BASE_URL%/}"
META_URL="$BASE_URL/v1/meta"
CHAT_URL="$BASE_URL/v1/chat-messages"
AUTH_HEADER="Authorization: Bearer ${APP_API_KEY}"

echo "Runtime endpoint: $CHAT_URL"
echo "Meta endpoint: $META_URL"

tmp_meta=$(mktemp)
meta_http=$(curl -sS -o "$tmp_meta" -w "%{http_code}" -X GET "$META_URL" -H "$AUTH_HEADER")
echo "Meta HTTP: $meta_http"
if [[ "$meta_http" != "200" ]]; then
  cat "$tmp_meta"
  exit 1
fi

for q in "${QUERIES[@]}"; do
  echo ""
  echo "=== Query ==="
  echo "$q"

  if [[ -n "$CONVERSATION_ID" ]]; then
    payload=$(jq -cn --arg q "$q" --arg user "$USER_ID" --arg cid "$CONVERSATION_ID" '{query:$q, inputs:{}, response_mode:"blocking", user:$user, conversation_id:$cid}')
  else
    payload=$(jq -cn --arg q "$q" --arg user "$USER_ID" '{query:$q, inputs:{}, response_mode:"blocking", user:$user}')
  fi

  tmp_out=$(mktemp)
  http_code=$(curl -sS -o "$tmp_out" -w "%{http_code}" -X POST "$CHAT_URL" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    --data "$payload")

  echo "HTTP: $http_code"
  if [[ "$http_code" != "200" ]]; then
    cat "$tmp_out"
    continue
  fi

  answer=$(jq -r '.answer // empty' "$tmp_out")
  current_conversation_id=$(jq -r '.conversation_id // empty' "$tmp_out")
  message_id=$(jq -r '.message_id // empty' "$tmp_out")

  if [[ -n "$current_conversation_id" ]]; then
    CONVERSATION_ID="$current_conversation_id"
  fi

  echo "Conversation ID: ${CONVERSATION_ID:-<none>}"
  echo "Message ID: ${message_id:-<none>}"
  echo "Answer preview:"
  printf '%s\n' "$answer" | sed -n '1,30p'
done
