#!/usr/bin/env bash
# Restore Knowledge Retrieval dataset from saved ID after Dify import.
# Usage: restore_kr_dataset.sh [--app-id <id>] [--auto-login]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) shift; DIFY_APP_ID="$1"; shift ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

ENV_FILE="$REPO_ROOT/.env"
SESSION_FILE="$REPO_ROOT/.secrets/dify_console_session.env"
set -a
[[ -f "$ENV_FILE" ]]     && source "$ENV_FILE"
[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
set +a

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
: "${DIFY_APP_ID:?DIFY_APP_ID is required}"

# Use DIFY_DATASET_ID from .env (single source of truth)
SAVED_ID="${DIFY_DATASET_ID:-<your-dataset-id>}"
echo "Using dataset ID from .env: ${SAVED_ID:0:40}..."

PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

"$PYTHON_BIN" << 'PYEOF'
import json, os

saved_id = open(os.environ["SAVED_ID_FILE"]).read().strip()
draft_url = f'{os.environ["DIFY_BASE_URL"].rstrip("/")}/console/api/apps/{os.environ["DIFY_APP_ID"]}/workflows/draft'

import subprocess
r = subprocess.run(['curl', '-sS', draft_url,
    '-H', f'Cookie: {os.environ["DIFY_CONSOLE_COOKIE"]}',
    '-H', f'x-csrf-token: {os.environ["DIFY_CSRF_TOKEN"]}'],
    capture_output=True, text=True)
draft = json.loads(r.stdout)

graph = draft.get("graph", {})
fixed = False
for node in graph.get("nodes", []):
    if node.get("id") == "17785930638200":
        node["data"]["dataset_ids"] = [saved_id]
        fixed = True
        print(f"Patched KR node dataset_ids")

if not fixed:
    print("KR node not found in draft")
    exit(1)

payload = {
    "graph": graph,
    "features": draft.get("features", {}),
    "environment_variables": draft.get("environment_variables", []),
    "conversation_variables": draft.get("conversation_variables", []),
    "hash": draft.get("hash", ""),
}

import tempfile
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(payload, f)
    tmp = f.name

r2 = subprocess.run(['curl', '-sS', '-X', 'POST', draft_url,
    '-H', f'Cookie: {os.environ["DIFY_CONSOLE_COOKIE"]}',
    '-H', f'x-csrf-token: {os.environ["DIFY_CSRF_TOKEN"]}',
    '-H', 'Content-Type: application/json',
    '--data', f'@{tmp}'], capture_output=True, text=True)
resp = json.loads(r2.stdout)
if resp.get('result') == 'success':
    print(f'Dataset restored ✓ (new hash: {str(resp.get("hash",""))[:20]}...)')
else:
    print(f'Failed: {json.dumps(resp)[:200]}')
os.unlink(tmp)
PYEOF
