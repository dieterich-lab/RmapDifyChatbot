#!/usr/bin/env bash
set -euo pipefail

usage() { echo "Usage: $0 <dsl-yaml-path> [--app-id <app-id>] [--allow-cookie-auth] [--auto-login]"; }
fail() { echo "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || fail "Python not found: $PYTHON_BIN"

[[ $# -ge 1 ]] || { usage; exit 1; }
DSL_PATH="$1"; shift
ALLOW_COOKIE_AUTH=0
AUTO_LOGIN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) shift; [[ $# -ge 1 ]] || fail "Missing value for --app-id"; DIFY_APP_ID="$1"; shift ;;
    --allow-cookie-auth) ALLOW_COOKIE_AUTH=1; shift ;;
    --auto-login) AUTO_LOGIN=1; shift ;;
    *) echo "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

[[ -f "$DSL_PATH" ]] || fail "DSL file not found: $DSL_PATH"

if [[ -n "${DIFY_API_KEY:-}" && -z "${DIFY_CONSOLE_API_KEY:-}" ]]; then
  if [[ "$ALLOW_COOKIE_AUTH" != "1" && ( -z "${DIFY_CONSOLE_COOKIE:-}" || -z "${DIFY_CSRF_TOKEN:-}" ) ]]; then
    fail "Detected DIFY_API_KEY but missing DIFY_CONSOLE_API_KEY. Use DIFY_CONSOLE_API_KEY or --allow-cookie-auth with DIFY_CONSOLE_COOKIE + DIFY_CSRF_TOKEN."
  fi
  echo "Detected DIFY_API_KEY without DIFY_CONSOLE_API_KEY; continuing with cookie fallback for /console/api endpoints."
fi

SESSION_DIR="$REPO_ROOT/.secrets"
SESSION_FILE="$SESSION_DIR/dify_console_session.env"
LOGIN_FILE="$SESSION_DIR/dify_console_login.env"
mkdir -p "$SESSION_DIR"
chmod 700 "$SESSION_DIR"

# Capture explicit env vars so they override sourced files.
EXPLICIT_KEYS=(
  DIFY_BASE_URL DIFY_CONSOLE_COOKIE DIFY_CSRF_TOKEN DIFY_APP_ID
  DIFY_CONSOLE_API_KEY DIFY_CONSOLE_EMAIL DIFY_CONSOLE_PASSWORD_B64
  DIFY_CONSOLE_PASSWORD DIFY_CONSOLE_LOGIN_LANGUAGE DIFY_CONSOLE_REMEMBER_ME
)
declare -A EXPLICIT=()
for key in "${EXPLICIT_KEYS[@]}"; do
  [[ ${!key+x} ]] && EXPLICIT["$key"]="${!key}"
done

[[ "${DIFY_CONSOLE_AUTO_LOGIN:-0}" == "1" ]] && AUTO_LOGIN=1
BOOTSTRAP_REQUESTED=0
[[ -n "${DIFY_CONSOLE_COOKIE:-}" ]] && BOOTSTRAP_REQUESTED=1

[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
[[ -f "$LOGIN_FILE" ]] && source "$LOGIN_FILE"
for key in "${!EXPLICIT[@]}"; do export "$key=${EXPLICIT[$key]}"; done

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"

persist_session() {
  [[ -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ]] || return 0
  umask 077
  cat >"$SESSION_FILE" <<EOF
DIFY_BASE_URL="${DIFY_BASE_URL}"
DIFY_CONSOLE_COOKIE="${DIFY_CONSOLE_COOKIE}"
DIFY_CSRF_TOKEN="${DIFY_CSRF_TOKEN}"
DIFY_APP_ID="${DIFY_APP_ID:-}"
EOF
}

if [[ "$BOOTSTRAP_REQUESTED" == "1" ]]; then
  : "${DIFY_CSRF_TOKEN:?DIFY_CSRF_TOKEN is required with DIFY_CONSOLE_COOKIE}"
  persist_session
  echo "Bootstrapped persistent session in $SESSION_FILE"
fi

IMPORT_URL="${DIFY_BASE_URL%/}/console/api/apps/imports"
PAYLOAD=$(DSL_PATH="$DSL_PATH" DIFY_APP_ID="${DIFY_APP_ID:-}" "$PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path
payload = {"mode": "yaml-content", "yaml_content": Path(os.environ["DSL_PATH"]).read_text(encoding="utf-8")}
app_id = (os.environ.get("DIFY_APP_ID") or "").strip()
if app_id:
    payload["app_id"] = app_id
print(json.dumps(payload, ensure_ascii=False))
PY
)

TMP_IMPORT=$(mktemp)
USED_AUTH_MODE=""

post_import_api() {
  curl -sS -o "$TMP_IMPORT" -w "%{http_code}" -X POST "$IMPORT_URL" \
    -H "Authorization: Bearer ${DIFY_CONSOLE_API_KEY}" \
    -H "Content-Type: application/json" --data "$PAYLOAD"
}

post_import_cookie() {
  : "${DIFY_CONSOLE_COOKIE:?No session found. Set DIFY_CONSOLE_COOKIE and DIFY_CSRF_TOKEN once.}"
  : "${DIFY_CSRF_TOKEN:?No session found. Set DIFY_CONSOLE_COOKIE and DIFY_CSRF_TOKEN once.}"
  curl -sS -o "$TMP_IMPORT" -w "%{http_code}" -X POST "$IMPORT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
    -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
    -H "Content-Type: application/json" --data "$PAYLOAD"
}

run_console_auto_login() {
  : "${DIFY_CONSOLE_EMAIL:?DIFY_CONSOLE_EMAIL is required for --auto-login}"

  if [[ -z "${DIFY_CONSOLE_PASSWORD_B64:-}" ]]; then
    : "${DIFY_CONSOLE_PASSWORD:?DIFY_CONSOLE_PASSWORD or DIFY_CONSOLE_PASSWORD_B64 is required for --auto-login}"
    DIFY_CONSOLE_PASSWORD_B64=$(printf '%s' "$DIFY_CONSOLE_PASSWORD" | base64 | tr -d '\n')
  fi

  local tmp_login tmp_headers login_url login_payload login_http parsed
  tmp_login=$(mktemp)
  tmp_headers=$(mktemp)
  login_url="${DIFY_BASE_URL%/}/console/api/login"

  login_payload=$(DIFY_CONSOLE_EMAIL="$DIFY_CONSOLE_EMAIL" DIFY_CONSOLE_PASSWORD_B64="$DIFY_CONSOLE_PASSWORD_B64" DIFY_CONSOLE_LOGIN_LANGUAGE="${DIFY_CONSOLE_LOGIN_LANGUAGE:-en-US}" DIFY_CONSOLE_REMEMBER_ME="${DIFY_CONSOLE_REMEMBER_ME:-true}" "$PYTHON_BIN" - <<'PY'
import json, os
remember = str(os.environ.get("DIFY_CONSOLE_REMEMBER_ME", "true")).strip().lower() in {"1", "true", "yes", "on"}
print(json.dumps({
    "email": os.environ["DIFY_CONSOLE_EMAIL"],
    "password": os.environ["DIFY_CONSOLE_PASSWORD_B64"],
    "language": os.environ.get("DIFY_CONSOLE_LOGIN_LANGUAGE", "en-US"),
    "remember_me": remember,
}, ensure_ascii=False))
PY
)

  login_http=$(curl -sS -D "$tmp_headers" -o "$tmp_login" -w "%{http_code}" -X POST "$login_url" \
    -H "Content-Type: application/json" --data "$login_payload")

  if [[ "$login_http" != "200" ]]; then
    echo "Console login failed (HTTP=$login_http)."
    cat "$tmp_login"
    return 1
  fi

  parsed=$(TMP_FILE="$tmp_login" TMP_HEADERS="$tmp_headers" "$PYTHON_BIN" - <<'PY'
import json, os
from http.cookies import SimpleCookie

o = json.load(open(os.environ["TMP_FILE"], encoding="utf-8"))
def pick(*path):
    cur = o
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

token = ""
for c in [pick("data", "access_token"), pick("access_token"), pick("data", "token"), pick("token"), pick("data", "value"), pick("value"), pick("result"), pick("result", "access_token"), pick("result", "token"), pick("result", "value")]:
    if isinstance(c, str) and c.strip():
        token = c.strip()
        break

cookie = SimpleCookie()
for line in open(os.environ["TMP_HEADERS"], encoding="utf-8"):
    if line.lower().startswith("set-cookie:"):
        cookie.load(line.split(":", 1)[1].strip())

parts = []
for name in ("access_token", "refresh_token", "csrf_token"):
    m = cookie.get(name)
    if m is not None:
        parts.append(f"{name}={m.value}")
csrf = cookie.get("csrf_token")

print(token)
print("; ".join(parts))
print(csrf.value if csrf is not None else "")
PY
)

  DIFY_CONSOLE_API_KEY=$(printf '%s\n' "$parsed" | sed -n '1p')
  DIFY_CONSOLE_COOKIE=$(printf '%s\n' "$parsed" | sed -n '2p')
  DIFY_CSRF_TOKEN=$(printf '%s\n' "$parsed" | sed -n '3p')

  [[ -n "$DIFY_CONSOLE_API_KEY" ]] || {
    echo "Console login succeeded but no access token found in response."
    cat "$tmp_login"
    return 1
  }

  export DIFY_CONSOLE_API_KEY
  if [[ -n "$DIFY_CONSOLE_COOKIE" && -n "$DIFY_CSRF_TOKEN" ]]; then
    export DIFY_CONSOLE_COOKIE DIFY_CSRF_TOKEN
    persist_session
    echo "Refreshed persistent console session in $SESSION_FILE"
  fi

  echo "Obtained console access token via /console/api/login."
}

run_import_with_retries() {
  HTTP_CODE=""

  if [[ -z "${DIFY_CONSOLE_API_KEY:-}" && "$AUTO_LOGIN" == "1" ]]; then
    echo "Auth mode: auto-login"
    run_console_auto_login
  fi

  if [[ -n "${DIFY_CONSOLE_API_KEY:-}" ]]; then
    echo "Auth mode: API key"
    HTTP_CODE=$(post_import_api)
    USED_AUTH_MODE="api_key"

    if [[ "$HTTP_CODE" == "401" && "$AUTO_LOGIN" == "1" ]]; then
      echo "Console auth failed (401); refreshing via /console/api/login."
      run_console_auto_login
      HTTP_CODE=$(post_import_api)
      USED_AUTH_MODE="api_key"
    fi

    if [[ "$HTTP_CODE" == "401" && ( "$ALLOW_COOKIE_AUTH" == "1" || ( -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ) ) ]]; then
      echo "API key not valid for console API on this deployment; retrying with cookie session."
      HTTP_CODE=$(post_import_cookie)
      USED_AUTH_MODE="cookie_fallback"
    fi
  else
    [[ "$ALLOW_COOKIE_AUTH" == "1" ]] || fail "DIFY_CONSOLE_API_KEY is missing. If your deployment does not support console API keys, provide DIFY_CONSOLE_COOKIE/DIFY_CSRF_TOKEN and use --allow-cookie-auth."
    echo "Auth mode: cookie fallback"
    HTTP_CODE=$(post_import_cookie)
    USED_AUTH_MODE="cookie_fallback"
  fi
}

run_import_with_retries

echo "Import endpoint: $IMPORT_URL"
echo "HTTP: $HTTP_CODE"
cat "$TMP_IMPORT"
echo

[[ "$HTTP_CODE" =~ ^20(0|1|2)$ ]] || exit 1
[[ "${AUTO_CONFIRM:-false}" == "true" ]] || exit 0

IMPORT_META=$(TMP_FILE="$TMP_IMPORT" "$PYTHON_BIN" - <<'PY'
import json, os
obj = json.load(open(os.environ["TMP_FILE"], encoding="utf-8"))
status = (obj.get("status") or (obj.get("data") or {}).get("status") or "").strip()
vals = [obj.get("id"), obj.get("import_id"), (obj.get("data") or {}).get("id"), (obj.get("data") or {}).get("import_id")]
print(status)
print(next((x for x in vals if x), ""))
PY
)

IMPORT_STATUS=$(printf '%s\n' "$IMPORT_META" | sed -n '1p')
IMPORT_ID=$(printf '%s\n' "$IMPORT_META" | sed -n '2p')

if [[ "$IMPORT_STATUS" == "completed" || "$IMPORT_STATUS" == "completed_with_warnings" ]]; then
  echo "Import already completed (status=$IMPORT_STATUS). Skipping confirm call."
  exit 0
fi

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
