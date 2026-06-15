#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 --app-id <app-id> --query <text> [--query <text> ...] [--classifier-node-id <id>] [--allow-cookie-auth] [--auto-login]"
  exit 1
fi

APP_ID=""
CLASSIFIER_NODE_ID="1778150713944"
CONVERSATION_ID=""
ALLOW_COOKIE_AUTH=0
AUTO_LOGIN=0
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
    --conversation-id)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --conversation-id"; exit 1; }
      CONVERSATION_ID="$1"
      shift
      ;;
    --allow-cookie-auth)
      ALLOW_COOKIE_AUTH=1
      shift
      ;;
    --auto-login)
      AUTO_LOGIN=1
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 --app-id <app-id> --query <text> [--query <text> ...] [--classifier-node-id <id>] [--allow-cookie-auth] [--auto-login]"
      exit 1
      ;;
  esac
done

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
[[ -n "$APP_ID" ]] || { echo "--app-id is required"; exit 1; }
[[ ${#QUERIES[@]} -gt 0 ]] || { echo "At least one --query is required"; exit 1; }

SESSION_DIR=".secrets"
SESSION_FILE="$SESSION_DIR/dify_console_session.env"
LOGIN_FILE="$SESSION_DIR/dify_console_login.env"

# Preserve explicit env values so they override persisted files.
IN_DIFY_BASE_URL="${DIFY_BASE_URL-}"
IN_DIFY_CONSOLE_COOKIE="${DIFY_CONSOLE_COOKIE-}"
IN_DIFY_CSRF_TOKEN="${DIFY_CSRF_TOKEN-}"
IN_DIFY_CONSOLE_API_KEY="${DIFY_CONSOLE_API_KEY-}"
IN_DIFY_CONSOLE_EMAIL="${DIFY_CONSOLE_EMAIL-}"
IN_DIFY_CONSOLE_PASSWORD_B64="${DIFY_CONSOLE_PASSWORD_B64-}"
IN_DIFY_CONSOLE_PASSWORD="${DIFY_CONSOLE_PASSWORD-}"
IN_DIFY_CONSOLE_LOGIN_LANGUAGE="${DIFY_CONSOLE_LOGIN_LANGUAGE-}"
IN_DIFY_CONSOLE_REMEMBER_ME="${DIFY_CONSOLE_REMEMBER_ME-}"

if [[ -f "$SESSION_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$SESSION_FILE"
fi

if [[ -f "$LOGIN_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOGIN_FILE"
fi

[[ -n "$IN_DIFY_BASE_URL" ]] && DIFY_BASE_URL="$IN_DIFY_BASE_URL"
[[ -n "$IN_DIFY_CONSOLE_COOKIE" ]] && DIFY_CONSOLE_COOKIE="$IN_DIFY_CONSOLE_COOKIE"
[[ -n "$IN_DIFY_CSRF_TOKEN" ]] && DIFY_CSRF_TOKEN="$IN_DIFY_CSRF_TOKEN"
[[ -n "$IN_DIFY_CONSOLE_API_KEY" ]] && DIFY_CONSOLE_API_KEY="$IN_DIFY_CONSOLE_API_KEY"
[[ -n "$IN_DIFY_CONSOLE_EMAIL" ]] && DIFY_CONSOLE_EMAIL="$IN_DIFY_CONSOLE_EMAIL"
[[ -n "$IN_DIFY_CONSOLE_PASSWORD_B64" ]] && DIFY_CONSOLE_PASSWORD_B64="$IN_DIFY_CONSOLE_PASSWORD_B64"
[[ -n "$IN_DIFY_CONSOLE_PASSWORD" ]] && DIFY_CONSOLE_PASSWORD="$IN_DIFY_CONSOLE_PASSWORD"
[[ -n "$IN_DIFY_CONSOLE_LOGIN_LANGUAGE" ]] && DIFY_CONSOLE_LOGIN_LANGUAGE="$IN_DIFY_CONSOLE_LOGIN_LANGUAGE"
[[ -n "$IN_DIFY_CONSOLE_REMEMBER_ME" ]] && DIFY_CONSOLE_REMEMBER_ME="$IN_DIFY_CONSOLE_REMEMBER_ME"

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"

# Guardrail: app runtime keys (usually prefix app-) do not authorize console endpoints.
# Do not hard-fail when cookie fallback is explicitly allowed or already configured.
if [[ -n "${DIFY_API_KEY:-}" && -z "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  if [[ "$ALLOW_COOKIE_AUTH" == "1" || ( -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ) ]]; then
    echo "Detected DIFY_API_KEY without DIFY_CONSOLE_API_KEY; continuing with cookie fallback for /console/api endpoints."
  else
    echo "Detected DIFY_API_KEY but missing DIFY_CONSOLE_API_KEY."
    echo "For draft console endpoints (/console/api), use DIFY_CONSOLE_API_KEY or --allow-cookie-auth with DIFY_CONSOLE_COOKIE + DIFY_CSRF_TOKEN."
    exit 1
  fi
fi

if [[ "${DIFY_CONSOLE_AUTO_LOGIN:-0}" == "1" ]]; then
  AUTO_LOGIN=1
fi

BASE_URL="${DIFY_BASE_URL%/}"
RUN_URL="$BASE_URL/console/api/apps/$APP_ID/advanced-chat/workflows/draft/run"

run_console_auto_login() {
  : "${DIFY_CONSOLE_EMAIL:?DIFY_CONSOLE_EMAIL is required for --auto-login}"

  if [[ -z "${DIFY_CONSOLE_PASSWORD_B64:-}" ]]; then
    : "${DIFY_CONSOLE_PASSWORD:?DIFY_CONSOLE_PASSWORD or DIFY_CONSOLE_PASSWORD_B64 is required for --auto-login}"
    DIFY_CONSOLE_PASSWORD_B64=$(printf '%s' "$DIFY_CONSOLE_PASSWORD" | base64 | tr -d '\n')
  fi

  local login_url="${DIFY_BASE_URL%/}/console/api/login"
  local login_lang="${DIFY_CONSOLE_LOGIN_LANGUAGE:-en-US}"
  local remember_me="${DIFY_CONSOLE_REMEMBER_ME:-true}"
  local login_payload
  login_payload=$(DIFY_CONSOLE_EMAIL="$DIFY_CONSOLE_EMAIL" DIFY_CONSOLE_PASSWORD_B64="$DIFY_CONSOLE_PASSWORD_B64" DIFY_CONSOLE_LOGIN_LANGUAGE="$login_lang" DIFY_CONSOLE_REMEMBER_ME="$remember_me" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import json
import os

remember = str(os.environ.get("DIFY_CONSOLE_REMEMBER_ME", "true")).strip().lower() in {"1", "true", "yes", "on"}
payload = {
  "email": os.environ["DIFY_CONSOLE_EMAIL"],
  "password": os.environ["DIFY_CONSOLE_PASSWORD_B64"],
  "language": os.environ.get("DIFY_CONSOLE_LOGIN_LANGUAGE", "en-US"),
  "remember_me": remember,
}
print(json.dumps(payload, ensure_ascii=False))
PY
)

  local tmp_login
  tmp_login=$(mktemp)
  local tmp_login_headers
  tmp_login_headers=$(mktemp)
  local login_http
  login_http=$(curl -sS -D "$tmp_login_headers" -o "$tmp_login" -w "%{http_code}" -X POST "$login_url" \
    -H "Content-Type: application/json" \
    --data "$login_payload")

  if [[ "$login_http" != "200" ]]; then
    echo "Console login failed (HTTP=$login_http)."
    cat "$tmp_login"
    return 1
  fi

  local token
  token=$(TMP_FILE="$tmp_login" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import json
import os

obj = json.load(open(os.environ["TMP_FILE"], encoding="utf-8"))

def pick(*paths):
    cur = obj
    for p in paths:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

candidates = [
    pick("data", "access_token"),
    pick("access_token"),
    pick("data", "token"),
    pick("token"),
    pick("data", "value"),
    pick("value"),
  pick("result"),
  pick("result", "access_token"),
  pick("result", "token"),
  pick("result", "value"),
]
for c in candidates:
    if isinstance(c, str) and c.strip():
        print(c.strip())
        break
PY
)

  if [[ -z "$token" ]]; then
    echo "Console login succeeded but no access token found in response."
    cat "$tmp_login"
    return 1
  fi

  DIFY_CONSOLE_API_KEY="$token"
  export DIFY_CONSOLE_API_KEY

  local cookie_bundle csrf_cookie
  cookie_bundle=$(TMP_HEADERS="$tmp_login_headers" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import os
from http.cookies import SimpleCookie

headers_path = os.environ["TMP_HEADERS"]
cookie = SimpleCookie()

with open(headers_path, encoding="utf-8") as fh:
    for line in fh:
        if line.lower().startswith("set-cookie:"):
            raw = line.split(":", 1)[1].strip()
            cookie.load(raw)

parts = []
for name in ("access_token", "refresh_token", "csrf_token"):
    morsel = cookie.get(name)
    if morsel is not None:
        parts.append(f"{name}={morsel.value}")

print("; ".join(parts))
PY
)

csrf_cookie=$(TMP_HEADERS="$tmp_login_headers" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import os
from http.cookies import SimpleCookie

headers_path = os.environ["TMP_HEADERS"]
cookie = SimpleCookie()

with open(headers_path, encoding="utf-8") as fh:
    for line in fh:
        if line.lower().startswith("set-cookie:"):
            raw = line.split(":", 1)[1].strip()
            cookie.load(raw)

m = cookie.get("csrf_token")
print(m.value if m is not None else "")
PY
)

  if [[ -n "$cookie_bundle" && -n "$csrf_cookie" ]]; then
    DIFY_CONSOLE_COOKIE="$cookie_bundle"
    DIFY_CSRF_TOKEN="$csrf_cookie"
  fi

  auth_mode="api-key"
  AUTH_HEADERS=(-H "Authorization: Bearer ${DIFY_CONSOLE_API_KEY}")
  echo "Obtained console access token via /console/api/login."
}

auth_mode=""
declare -a AUTH_HEADERS=()

if [[ -z "${DIFY_CONSOLE_API_KEY:-}" && "$AUTO_LOGIN" == "1" ]]; then
  echo "Auth mode: auto-login"
  run_console_auto_login
fi

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

  if [[ -n "$CONVERSATION_ID" ]]; then
    payload=$(jq -cn --arg q "$q" --arg cid "$CONVERSATION_ID" '{query:$q, inputs:{}, files:[], response_mode:"streaming", user:"route-debug-script", conversation_id:$cid}')
  else
    payload=$(jq -cn --arg q "$q" '{query:$q, inputs:{}, files:[], response_mode:"streaming", user:"route-debug-script"}')
  fi
  tmp_out=$(mktemp)
  http_code=$(curl -sS -o "$tmp_out" -w "%{http_code}" -X POST "$RUN_URL" \
    "${AUTH_HEADERS[@]}" \
    -H "Content-Type: application/json" \
    --data "$payload")

  if [[ "$http_code" == "401" ]] && [[ "$AUTO_LOGIN" == "1" ]]; then
    echo "Console auth failed (401); refreshing via /console/api/login."
    run_console_auto_login
    http_code=$(curl -sS -o "$tmp_out" -w "%{http_code}" -X POST "$RUN_URL" \
      "${AUTH_HEADERS[@]}" \
      -H "Content-Type: application/json" \
      --data "$payload")

    if [[ "$http_code" == "401" ]] && [[ -n "${DIFY_CONSOLE_COOKIE:-}" ]] && [[ -n "${DIFY_CSRF_TOKEN:-}" ]]; then
      echo "API key auth still unauthorized; retrying with refreshed cookie session."
      http_code=$(curl -sS -o "$tmp_out" -w "%{http_code}" -X POST "$RUN_URL" \
        -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
        -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "$payload")
    fi
  fi

  echo "HTTP: $http_code"
  if [[ "$http_code" != "200" ]]; then
    cat "$tmp_out"
    continue
  fi

  # Parsing SSE can legitimately yield no rows for a selector; avoid aborting under pipefail.
  set +e
  class_name=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r --arg id "$CLASSIFIER_NODE_ID" 'select(.event=="node_finished" and .data.node_id==$id) | .data.outputs.class_name' | tail -n1)
  class_id=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r --arg id "$CLASSIFIER_NODE_ID" 'select(.event=="node_finished" and .data.node_id==$id) | .data.outputs.class_id' | tail -n1)
  answer=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r 'select(.event=="message") | .answer' | tr -d '\r' | paste -sd '' - | perl -0777 -pe 's/<think>.*?<\/think>//sg')
  current_conversation_id=$(grep '^data: ' "$tmp_out" | sed 's/^data: //' | jq -r '(.conversation_id // .data.conversation_id // empty)' | head -n1)
  set -e
  if [[ -n "$current_conversation_id" ]]; then
    CONVERSATION_ID="$current_conversation_id"
  fi

  echo "Classifier node: $CLASSIFIER_NODE_ID"
  echo "Conversation ID: ${CONVERSATION_ID:-<none>}"
  echo "Class ID: ${class_id:-<none>}"
  echo "Class Name: ${class_name:-<none>}"
  echo "Answer preview:"
  printf '%s\n' "$answer" | sed -n '1,20p'
done
