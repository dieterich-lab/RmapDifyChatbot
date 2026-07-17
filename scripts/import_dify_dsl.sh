#!/usr/bin/env bash
set -euo pipefail

usage() { echo "Usage: $0 <dsl-yaml-path> [--app-id <app-id>] [--allow-cookie-auth] [--auto-login] [--skip-build]"; }
fail() { echo "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || fail "Python not found: $PYTHON_BIN"

[[ $# -ge 1 ]] || { usage; exit 1; }
DSL_PATH="$1"; shift
ALLOW_COOKIE_AUTH=0
AUTO_LOGIN=0
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) shift; [[ $# -ge 1 ]] || fail "Missing value for --app-id"; DIFY_APP_ID="$1"; shift ;;
    --allow-cookie-auth) ALLOW_COOKIE_AUTH=1; shift ;;
    --auto-login) AUTO_LOGIN=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
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
ENV_FILE="$REPO_ROOT/.env"
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

[[ -f "$ENV_FILE" ]]     && source "$ENV_FILE"
[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
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

# ── Pre-import: build DSL from workflow_scripts/ ──────────────────────────
if [[ "$SKIP_BUILD" != "1" ]]; then
  BUILD_SCRIPT="$REPO_ROOT/scripts/build_dsl.py"
  if [[ -x "$BUILD_SCRIPT" || -f "$BUILD_SCRIPT" ]]; then
    echo "Building DSL from workflow_scripts/..."
    "$PYTHON_BIN" "$BUILD_SCRIPT" || fail "DSL build failed"
    echo ""
  fi
fi

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

  # Prefer cookie auth if session exists, otherwise use API key or auto-login
  if [[ -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ]]; then
    echo "Auth mode: cookie session"
    HTTP_CODE=$(post_import_cookie)
    USED_AUTH_MODE="cookie"

    if [[ "$HTTP_CODE" == "401" && "$AUTO_LOGIN" == "1" ]]; then
      echo "Session expired; refreshing via /console/api/login."
      run_console_auto_login
      HTTP_CODE=$(post_import_cookie)
      USED_AUTH_MODE="cookie"
    fi
  elif [[ -n "${DIFY_CONSOLE_API_KEY:-}" ]]; then
    echo "Auth mode: API key"
    HTTP_CODE=$(post_import_api)
    USED_AUTH_MODE="api_key"

    if [[ "$HTTP_CODE" == "401" && "$AUTO_LOGIN" == "1" ]]; then
      echo "Console auth failed (401); refreshing via /console/api/login."
      run_console_auto_login
      HTTP_CODE=$(post_import_api)
      USED_AUTH_MODE="api_key"
    fi
  elif [[ "$AUTO_LOGIN" == "1" ]]; then
    echo "Auth mode: auto-login"
    run_console_auto_login
    HTTP_CODE=$(post_import_cookie)
    USED_AUTH_MODE="cookie"
  else
    fail "No authentication available. Provide DIFY_CONSOLE_API_KEY, or DIFY_CONSOLE_COOKIE/DIFY_CSRF_TOKEN, or use --auto-login."
  fi
}

# ── Draft sync ──────────────────────────────────────────────────────────────
# Always sync the draft so the GUI editor reflects the imported DSL.
sync_draft() {
  [[ -n "${DIFY_APP_ID:-}" ]] || { echo "Skipping draft sync: DIFY_APP_ID not set."; return 0; }
  [[ -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ]] || {
    echo "Skipping draft sync: no cookie session available."; return 0
  }

  DRAFT_URL="${DIFY_BASE_URL%/}/console/api/apps/${DIFY_APP_ID}/workflows/draft"
  TMP_DRAFT_GET=$(mktemp)
  TMP_DRAFT_PAYLOAD=$(mktemp)
  TMP_DRAFT_RESP=$(mktemp)

  # Fetch current draft to get the hash required for the update
  DRAFT_GET_HTTP=$(curl -sS -o "$TMP_DRAFT_GET" -w "%{http_code}" "$DRAFT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" -H "x-csrf-token: ${DIFY_CSRF_TOKEN}")
  if [[ "$DRAFT_GET_HTTP" != "200" ]]; then
    echo "Warning: could not fetch draft (HTTP $DRAFT_GET_HTTP); skipping draft sync."
    return 0
  fi

  # Build draft payload: graph + features from DSL, env/conv vars from current draft
  DSL_PATH="$DSL_PATH" TMP_DRAFT_GET="$TMP_DRAFT_GET" TMP_DRAFT_PAYLOAD="$TMP_DRAFT_PAYLOAD" \
  "$PYTHON_BIN" - <<'PY'
import json, os, yaml
from pathlib import Path
dsl   = yaml.safe_load(Path(os.environ["DSL_PATH"]).read_text(encoding="utf-8"))
draft = json.loads(Path(os.environ["TMP_DRAFT_GET"]).read_text(encoding="utf-8"))
payload = {
    "graph":                 dsl["workflow"]["graph"],
    "features":              dsl.get("features", {}),
    "environment_variables": draft.get("environment_variables", []),
    "conversation_variables":draft.get("conversation_variables", []),
    "hash":                  draft.get("hash", ""),
}
with open(os.environ["TMP_DRAFT_PAYLOAD"], "w") as f:
    json.dump(payload, f, ensure_ascii=False)
g = dsl["workflow"]["graph"]
print(f"Draft payload: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
PY

  # Post to draft endpoint
  DRAFT_POST_HTTP=$(curl -sS -o "$TMP_DRAFT_RESP" -w "%{http_code}" \
    -X POST "$DRAFT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
    -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
    -H "Content-Type: application/json" \
    --data @"$TMP_DRAFT_PAYLOAD")

  echo "Draft sync HTTP: $DRAFT_POST_HTTP"
  "$PYTHON_BIN" -c "
import json
d = json.load(open('$TMP_DRAFT_RESP'))
if d.get('result') == 'success':
    print(f'Draft updated ✓  (new hash: {str(d.get(\"hash\",\"\"))[:20]}...)')
else:
    print('Draft sync failed:', json.dumps(d)[:300])
  "
}

# ── KR dataset fix ─────────────────────────────────────────────────────────
# Dify import strips dataset_ids from Knowledge Retrieval nodes.
# This function restores them from saved ID or Meta Routing config.
fix_kr_dataset() {
  [[ -n "${DIFY_APP_ID:-}" ]] || { echo "Skipping KR dataset fix: DIFY_APP_ID not set."; return 0; }
  [[ -n "${DIFY_CONSOLE_COOKIE:-}" && -n "${DIFY_CSRF_TOKEN:-}" ]] || {
    echo "Skipping KR dataset fix: no cookie session available."; return 0
  }

  DRAFT_URL="${DIFY_BASE_URL%/}/console/api/apps/${DIFY_APP_ID}/workflows/draft"
  TMP_KR_GET=$(mktemp)
  TMP_KR_PAYLOAD=$(mktemp)
  TMP_KR_RESP=$(mktemp)
  TMP_KR_PY=$(mktemp)

  DRAFT_GET_HTTP=$(curl -sS -o "$TMP_KR_GET" -w "%{http_code}" "$DRAFT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" -H "x-csrf-token: ${DIFY_CSRF_TOKEN}")
  if [[ "$DRAFT_GET_HTTP" != "200" ]]; then
    echo "Warning: could not fetch draft for KR fix (HTTP $DRAFT_GET_HTTP)."
    return 0
  fi

  cat > "$TMP_KR_PY" << 'PYEOF'
import json, os, sys

draft = json.load(open(os.environ["TMP_KR_GET"], encoding="utf-8"))
graph = draft.get("graph", {})

for node in graph.get("nodes", []):
    if node.get("id") == "17785930638200":
        dids = node.get("data", {}).get("dataset_ids", [])
        if dids and len(dids) > 0 and dids[0]:
            print("unchanged")
            sys.exit(0)

        # Try saved ID first
        saved_file = os.environ.get("SAVED_ID_FILE", "")
        if saved_file and os.path.isfile(saved_file):
            saved = open(saved_file).read().strip()
            if saved:
                node["data"]["dataset_ids"] = [saved]
                # Write back modified draft and build payload
                payload = {
                    "graph": graph,
                    "features": draft.get("features", {}),
                    "environment_variables": draft.get("environment_variables", []),
                    "conversation_variables": draft.get("conversation_variables", []),
                    "hash": draft.get("hash", ""),
                }
                json.dump(payload, open(os.environ["TMP_KR_PAYLOAD"], "w"))
                print("fixed")
                sys.exit(0)

        # Fallback: Meta Routing config
        try:
            import yaml
            with open(os.environ["META_ROUTING_YML"]) as f:
                mr = yaml.safe_load(f)
            for n in mr["workflow"]["graph"]["nodes"]:
                if "Knowledge Retrieval" in n.get("data", {}).get("title", ""):
                    ref = n["data"].get("dataset_ids", [])
                    if ref and ref[0]:
                        node["data"]["dataset_ids"] = ref
                        payload = {
                            "graph": graph,
                            "features": draft.get("features", {}),
                            "environment_variables": draft.get("environment_variables", []),
                            "conversation_variables": draft.get("conversation_variables", []),
                            "hash": draft.get("hash", ""),
                        }
                        json.dump(payload, open(os.environ["TMP_KR_PAYLOAD"], "w"))
                        print("fixed")
                        sys.exit(0)
        except Exception as e:
            print(f"error:fallback_failed:{e}")
            sys.exit(1)

        print("unchanged")
        sys.exit(0)

print("unchanged")
PYEOF

  local fixed
  fixed=$(TMP_KR_GET="$TMP_KR_GET" \
    TMP_KR_PAYLOAD="$TMP_KR_PAYLOAD" \
    SAVED_ID_FILE="$REPO_ROOT/.secrets/kr_dataset_id.txt" \
    META_ROUTING_YML="$REPO_ROOT/config/RMAP Chatbot Meta Routing.yml" \
    "$PYTHON_BIN" "$TMP_KR_PY")

  if [[ "$fixed" == "unchanged" ]]; then
    echo "KR dataset: unchanged."
    return 0
  elif [[ "$fixed" != "fixed" ]]; then
    echo "KR dataset fix skipped: $fixed"
    return 0
  fi

  # Post updated draft (payload already built by fix script)
  KR_POST_HTTP=$(curl -sS -o "$TMP_KR_RESP" -w "%{http_code}" \
    -X POST "$DRAFT_URL" \
    -H "Cookie: ${DIFY_CONSOLE_COOKIE}" \
    -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
    -H "Content-Type: application/json" \
    --data @"$TMP_KR_PAYLOAD")

  echo "KR dataset fix HTTP: $KR_POST_HTTP"
  "$PYTHON_BIN" -c "
import json
d = json.load(open('$TMP_KR_RESP'))
if d.get('result') == 'success':
    print('KR dataset restored ✓')
else:
    print('KR fix may have failed:', json.dumps(d)[:200])
"
}

run_import_with_retries

echo "Import endpoint: $IMPORT_URL"
echo "HTTP: $HTTP_CODE"
cat "$TMP_IMPORT"
echo

[[ "$HTTP_CODE" =~ ^20(0|1|2)$ ]] || exit 1

sync_draft

fix_kr_dataset

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
