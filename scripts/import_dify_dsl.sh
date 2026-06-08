#!/usr/bin/env bash
set -euo pipefail

# Minimal Dify DSL import helper.
# Preferred auth (stable for automation):
#   DIFY_BASE_URL=... DIFY_CONSOLE_API_KEY='...' scripts/import_dify_dsl.sh <dsl.yml>
# Optional cookie fallback (explicit opt-in only):
#   DIFY_BASE_URL=... DIFY_CONSOLE_COOKIE='...' DIFY_CSRF_TOKEN='...' scripts/import_dify_dsl.sh <dsl.yml> --allow-cookie-auth
# Optional login-based token refresh (for deployments without static console API keys):
#   DIFY_CONSOLE_EMAIL='...' DIFY_CONSOLE_PASSWORD_B64='...' scripts/import_dify_dsl.sh <dsl.yml> --auto-login
# Update existing app (avoid duplicates):
#   DIFY_APP_ID=<existing-app-id> scripts/import_dify_dsl.sh <dsl.yml>

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <dsl-yaml-path> [--app-id <app-id>] [--allow-cookie-auth] [--auto-login]"
  exit 1
fi

DSL_PATH="$1"
shift
ALLOW_COOKIE_AUTH=0
AUTO_LOGIN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id)
      shift
      [[ $# -ge 1 ]] || { echo "Missing value for --app-id"; exit 1; }
      DIFY_APP_ID="$1"
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
      echo "Usage: $0 <dsl-yaml-path> [--app-id <app-id>] [--allow-cookie-auth] [--auto-login]"
      exit 1
      ;;
  esac
done

[[ -f "$DSL_PATH" ]] || { echo "DSL file not found: $DSL_PATH"; exit 1; }

# Guardrail: app runtime keys (usually prefix app-) do not authorize console endpoints.
# Do not hard-fail when cookie fallback is explicitly allowed or already configured.
if [[ -n "${DIFY_API_KEY:-}" && -z "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  if [[ "$ALLOW_COOKIE_AUTH" == "1" || ( -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ) ]]; then
    echo "Detected DIFY_API_KEY without DIFY_CONSOLE_API_KEY; continuing with cookie fallback for /console/api endpoints."
  else
    echo "Detected DIFY_API_KEY but missing DIFY_CONSOLE_API_KEY."
    echo "For console import endpoints (/console/api), use DIFY_CONSOLE_API_KEY or --allow-cookie-auth with DIFY_CONSOLE_COOKIE + DIFY_CSRF_TOKEN."
    exit 1
  fi
fi

SESSION_DIR=".secrets"
SESSION_FILE="$SESSION_DIR/dify_console_session.env"
LOGIN_FILE="$SESSION_DIR/dify_console_login.env"
mkdir -p "$SESSION_DIR"
chmod 700 "$SESSION_DIR"

# Keep track of values explicitly provided for this run (env should win over file).
IN_DIFY_BASE_URL="${DIFY_BASE_URL-}"
IN_DIFY_CONSOLE_COOKIE="${DIFY_CONSOLE_COOKIE-}"
IN_DIFY_CSRF_TOKEN="${DIFY_CSRF_TOKEN-}"
IN_DIFY_APP_ID="${DIFY_APP_ID-}"
IN_DIFY_APP_ID_IS_SET=0
[[ ${DIFY_APP_ID+x} ]] && IN_DIFY_APP_ID_IS_SET=1
IN_DIFY_CONSOLE_API_KEY="${DIFY_CONSOLE_API_KEY-}"
IN_DIFY_CONSOLE_EMAIL="${DIFY_CONSOLE_EMAIL-}"
IN_DIFY_CONSOLE_PASSWORD_B64="${DIFY_CONSOLE_PASSWORD_B64-}"
IN_DIFY_CONSOLE_LOGIN_LANGUAGE="${DIFY_CONSOLE_LOGIN_LANGUAGE-}"
IN_DIFY_CONSOLE_REMEMBER_ME="${DIFY_CONSOLE_REMEMBER_ME-}"
if [[ "${DIFY_CONSOLE_AUTO_LOGIN:-0}" == "1" ]]; then
  AUTO_LOGIN=1
fi
BOOTSTRAP_REQUESTED=0
[[ -n "$IN_DIFY_CONSOLE_COOKIE" ]] && BOOTSTRAP_REQUESTED=1

# Load persisted session values when present.
if [[ -f "$SESSION_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$SESSION_FILE"
fi

# Load persisted login credentials (separate file so cookie bootstrap does not overwrite them).
if [[ -f "$LOGIN_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOGIN_FILE"
fi

# Restore explicit run-time values so they override persisted session state.
[[ -n "$IN_DIFY_BASE_URL" ]] && DIFY_BASE_URL="$IN_DIFY_BASE_URL"
[[ -n "$IN_DIFY_CONSOLE_COOKIE" ]] && DIFY_CONSOLE_COOKIE="$IN_DIFY_CONSOLE_COOKIE"
[[ -n "$IN_DIFY_CSRF_TOKEN" ]] && DIFY_CSRF_TOKEN="$IN_DIFY_CSRF_TOKEN"
if [[ "$IN_DIFY_APP_ID_IS_SET" == "1" ]]; then
  DIFY_APP_ID="$IN_DIFY_APP_ID"
fi
[[ -n "$IN_DIFY_CONSOLE_API_KEY" ]] && DIFY_CONSOLE_API_KEY="$IN_DIFY_CONSOLE_API_KEY"
[[ -n "$IN_DIFY_CONSOLE_EMAIL" ]] && DIFY_CONSOLE_EMAIL="$IN_DIFY_CONSOLE_EMAIL"
[[ -n "$IN_DIFY_CONSOLE_PASSWORD_B64" ]] && DIFY_CONSOLE_PASSWORD_B64="$IN_DIFY_CONSOLE_PASSWORD_B64"
[[ -n "$IN_DIFY_CONSOLE_LOGIN_LANGUAGE" ]] && DIFY_CONSOLE_LOGIN_LANGUAGE="$IN_DIFY_CONSOLE_LOGIN_LANGUAGE"
[[ -n "$IN_DIFY_CONSOLE_REMEMBER_ME" ]] && DIFY_CONSOLE_REMEMBER_ME="$IN_DIFY_CONSOLE_REMEMBER_ME"

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"

# One-time bootstrap from browser request headers (only when explicitly provided now).
if [[ "$BOOTSTRAP_REQUESTED" == "1" ]]; then
  : "${DIFY_CSRF_TOKEN:?DIFY_CSRF_TOKEN is required with DIFY_CONSOLE_COOKIE}"
  umask 077
  cat >"$SESSION_FILE" <<EOF
DIFY_BASE_URL="${DIFY_BASE_URL}"
DIFY_CONSOLE_COOKIE="${DIFY_CONSOLE_COOKIE}"
DIFY_CSRF_TOKEN="${DIFY_CSRF_TOKEN}"
DIFY_APP_ID="${DIFY_APP_ID:-}"
EOF
  echo "Bootstrapped persistent session in $SESSION_FILE"
fi

IMPORT_URL="${DIFY_BASE_URL%/}/console/api/apps/imports"
PAYLOAD=$(DSL_PATH="$DSL_PATH" DIFY_APP_ID="${DIFY_APP_ID:-}" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import json, os
from pathlib import Path

payload = {
  "mode": "yaml-content",
  "yaml_content": Path(os.environ["DSL_PATH"]).read_text(encoding="utf-8"),
}
app_id = (os.environ.get("DIFY_APP_ID") or "").strip()
if app_id:
  payload["app_id"] = app_id

print(json.dumps(payload, ensure_ascii=False))
PY
)

TMP_IMPORT=$(mktemp)
USED_AUTH_MODE=""

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
  local login_http
  login_http=$(curl -sS -o "$tmp_login" -w "%{http_code}" -X POST "$login_url" \
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
  echo "Obtained console access token via /console/api/login."
}

run_import_with_api_key() {
  curl -sS -o "$TMP_IMPORT" -w "%{http_code}" -X POST "$IMPORT_URL" \
    -H "Authorization: Bearer ${DIFY_CONSOLE_API_KEY}" \
    -H "Content-Type: application/json" \
    --data "$PAYLOAD"
}

run_import_with_cookie() {
  : "${DIFY_CONSOLE_COOKIE:?No session found. Set DIFY_CONSOLE_COOKIE and DIFY_CSRF_TOKEN once.}"
  : "${DIFY_CSRF_TOKEN:?No session found. Set DIFY_CONSOLE_COOKIE and DIFY_CSRF_TOKEN once.}"
  curl -sS -o "$TMP_IMPORT" -w "%{http_code}" -X POST "$IMPORT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
    -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "$PAYLOAD"
}

if [[ -z "${DIFY_CONSOLE_API_KEY:-}" && "$AUTO_LOGIN" == "1" ]]; then
  echo "Auth mode: auto-login"
  run_console_auto_login
fi

if [[ -n "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  echo "Auth mode: API key"
  HTTP_CODE=$(run_import_with_api_key)
  USED_AUTH_MODE="api_key"

  if [[ "$HTTP_CODE" == "401" ]] && grep -qi 'Invalid token' "$TMP_IMPORT"; then
    if [[ "$AUTO_LOGIN" == "1" ]]; then
      echo "Console token invalid; refreshing via /console/api/login."
      run_console_auto_login
      HTTP_CODE=$(run_import_with_api_key)
      USED_AUTH_MODE="api_key"
    fi

    if [[ "$ALLOW_COOKIE_AUTH" == "1" || ( -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ) ]]; then
      echo "API key not valid for console API on this deployment; retrying with cookie session."
      HTTP_CODE=$(run_import_with_cookie)
      USED_AUTH_MODE="cookie_fallback"
    fi
  fi
else
  if [[ "$ALLOW_COOKIE_AUTH" != "1" ]]; then
    echo "DIFY_CONSOLE_API_KEY is missing."
    echo "If your deployment does not support console API keys, provide DIFY_CONSOLE_COOKIE/DIFY_CSRF_TOKEN and use --allow-cookie-auth."
    exit 1
  fi
  echo "Auth mode: cookie fallback"
  HTTP_CODE=$(run_import_with_cookie)
  USED_AUTH_MODE="cookie_fallback"
fi

echo "Import endpoint: $IMPORT_URL"
echo "HTTP: $HTTP_CODE"
cat "$TMP_IMPORT"
echo

[[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" || "$HTTP_CODE" == "202" ]] || exit 1
[[ "${AUTO_CONFIRM:-false}" == "true" ]] || exit 0

IMPORT_STATUS=$(TMP_FILE="$TMP_IMPORT" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import json, os
obj = json.load(open(os.environ["TMP_FILE"], encoding="utf-8"))
print((obj.get("status") or (obj.get("data") or {}).get("status") or "").strip())
PY
)
[[ "$IMPORT_STATUS" == "completed" || "$IMPORT_STATUS" == "completed_with_warnings" ]] && {
  echo "Import already completed (status=$IMPORT_STATUS). Skipping confirm call."
  exit 0
}

IMPORT_ID=$(TMP_FILE="$TMP_IMPORT" /home/pwiesenbach/rmap-chatbot/.venv/bin/python - <<'PY'
import json, os
obj = json.load(open(os.environ["TMP_FILE"], encoding="utf-8"))
for x in [obj.get("id"), obj.get("import_id"), (obj.get("data") or {}).get("id"), (obj.get("data") or {}).get("import_id")]:
    if x:
        print(x)
        break
PY
)

[[ -n "$IMPORT_ID" ]] || { echo "No import ID found; skipping confirm."; exit 0; }

CONFIRM_URL="${DIFY_BASE_URL%/}/console/api/apps/imports/${IMPORT_ID}/confirm"
TMP_CONFIRM=$(mktemp)
if [[ "$USED_AUTH_MODE" == "api_key" ]]; then
  HTTP_CONFIRM=$(curl -sS -o "$TMP_CONFIRM" -w "%{http_code}" -X POST "$CONFIRM_URL" \
    -H "Authorization: Bearer ${DIFY_CONSOLE_API_KEY}" \
    -H "Content-Type: application/json" --data '{}')
else
  HTTP_CONFIRM=$(curl -sS -o "$TMP_CONFIRM" -w "%{http_code}" -X POST "$CONFIRM_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
    -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
    -H "Content-Type: application/json" --data '{}')
fi

echo "Confirm endpoint: $CONFIRM_URL"
echo "HTTP: $HTTP_CONFIRM"
cat "$TMP_CONFIRM"
echo
