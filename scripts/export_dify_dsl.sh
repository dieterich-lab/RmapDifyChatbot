#!/usr/bin/env bash
# Export the current Dify draft workflow as a DSL YAML file.
# Usage: export_dify_dsl.sh <output-path> [--app-id <id>] [--auto-login]
set -euo pipefail

fail() { echo "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || fail "Python not found: $PYTHON_BIN"

[[ $# -ge 1 ]] || { echo "Usage: $0 <output-path> [--app-id <id>] [--auto-login]"; exit 1; }
OUT_PATH="$1"; shift
AUTO_LOGIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) shift; DIFY_APP_ID="$1"; shift ;;
    --auto-login) AUTO_LOGIN=1; shift ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

SESSION_FILE="$REPO_ROOT/.secrets/dify_console_session.env"
LOGIN_FILE="$REPO_ROOT/.secrets/dify_console_login.env"
set -a
[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
[[ -f "$LOGIN_FILE" ]]   && source "$LOGIN_FILE"
set +a

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
: "${DIFY_APP_ID:?DIFY_APP_ID is required}"

# ---- Auth: auto-login -------------------------------------------------------
if [[ "$AUTO_LOGIN" == "1" ]]; then
  : "${DIFY_CONSOLE_EMAIL:?DIFY_CONSOLE_EMAIL is required for --auto-login}"

  tmp_body=$(mktemp); tmp_hdrs=$(mktemp)
  login_payload=$("$PYTHON_BIN" -c "
import json, os, base64
pw = os.environ.get('DIFY_CONSOLE_PASSWORD_B64') or ''
if not pw and os.environ.get('DIFY_CONSOLE_PASSWORD'):
    pw = base64.b64encode(os.environ['DIFY_CONSOLE_PASSWORD'].encode()).decode()
if not pw: raise SystemExit('DIFY_CONSOLE_PASSWORD_B64 or DIFY_CONSOLE_PASSWORD is required')
print(json.dumps({'email': os.environ['DIFY_CONSOLE_EMAIL'], 'password': pw, 'language': os.environ.get('DIFY_CONSOLE_LOGIN_LANGUAGE','en-US'), 'remember_me': True}))
")
  login_http=$(curl -sS -D "$tmp_hdrs" -o "$tmp_body" -w "%{http_code}" -X POST \
    "${DIFY_BASE_URL%/}/console/api/login" \
    -H "Content-Type: application/json" --data "$login_payload")
  [[ "$login_http" == "200" ]] || { echo "Login failed (HTTP $login_http):"; cat "$tmp_body"; exit 1; }

  eval "$("$PYTHON_BIN" - "$tmp_hdrs" <<'PY'
import sys
from http.cookies import SimpleCookie
cookie = SimpleCookie()
for line in open(sys.argv[1]):
    if line.lower().startswith("set-cookie:"):
        cookie.load(line.split(":",1)[1].strip())
parts = [f"{n}={cookie[n].value}" for n in ("access_token","refresh_token","csrf_token") if n in cookie]
csrf  = cookie["csrf_token"].value if "csrf_token" in cookie else ""
print(f'DIFY_CONSOLE_COOKIE="{"; ".join(parts)}"')
print(f'DIFY_CSRF_TOKEN="{csrf}"')
PY
  )"
  echo "Auth mode: auto-login — session refreshed"
fi

# ---- Export -----------------------------------------------------------------
: "${DIFY_CONSOLE_COOKIE:?No session cookie. Use --auto-login or set DIFY_CONSOLE_COOKIE.}"
: "${DIFY_CSRF_TOKEN:?No CSRF token. Use --auto-login or set DIFY_CSRF_TOKEN.}"

TMP_JSON=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$TMP_JSON" -w "%{http_code}" \
  "${DIFY_BASE_URL%/}/console/api/apps/${DIFY_APP_ID}/export?include_secret=false" \
  -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
  -H "x-csrf-token: ${DIFY_CSRF_TOKEN}")

[[ "$HTTP_STATUS" == "200" ]] || { echo "Export failed (HTTP $HTTP_STATUS):"; cat "$TMP_JSON"; exit 1; }

"$PYTHON_BIN" - "$TMP_JSON" "$OUT_PATH" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
yaml_content = data.get("data") or data.get("yaml_content") or ""
if not yaml_content:
    print("Error: no YAML content in export response", file=sys.stderr); sys.exit(1)
open(sys.argv[2], "w").write(yaml_content)
print(f"Exported {len(yaml_content)} chars to {sys.argv[2]}")
PY
