#!/usr/bin/env bash
# Fix the Knowledge Retrieval dataset after Dify import.
# Usage: fix_kr_dataset.sh [--app-id <id>] [--auto-login]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AUTO_LOGIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) shift; DIFY_APP_ID="$1"; shift ;;
    --auto-login) AUTO_LOGIN=1; shift ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

SESSION_FILE="$REPO_ROOT/.secrets/dify_console_session.env"
ENV_FILE="$REPO_ROOT/.env"
set -a
[[ -f "$ENV_FILE" ]]     && source "$ENV_FILE"
[[ -f "$SESSION_FILE" ]] && source "$SESSION_FILE"
set +a

: "${DIFY_BASE_URL:?DIFY_BASE_URL is required}"
: "${DIFY_APP_ID:?DIFY_APP_ID is required}"
: "${DIFY_CONSOLE_COOKIE:?No session. Use --auto-login first.}"
: "${DIFY_CSRF_TOKEN:?No session. Use --auto-login first.}"

BASE="${DIFY_BASE_URL%/}"
DRAFT_URL="$BASE/console/api/apps/${DIFY_APP_ID}/workflows/draft"

PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

echo "Fixing Knowledge Retrieval dataset..."

# Fetch current draft
TMP_DRAFT=$(mktemp)
HTTP=$(curl -sS -o "$TMP_DRAFT" -w "%{http_code}" "$DRAFT_URL" \
  -H "Cookie: ${DIFY_CONSOLE_COOKIE}" -H "x-csrf-token: ${DIFY_CSRF_TOKEN}")

if [[ "$HTTP" != "200" ]]; then
  echo "Failed to fetch draft (HTTP $HTTP)"
  cat "$TMP_DRAFT"
  exit 1
fi

# Build new draft with fixed dataset
TMP_PAYLOAD=$(mktemp)
TMP_RESP=$(mktemp)

"$PYTHON_BIN" << 'PYEOF'
import json, os

draft = json.load(open(os.environ["TMP_DRAFT"], encoding="utf-8"))
graph = draft.get("graph", {})

# Find Knowledge Retrieval node and fix dataset_ids
for node in graph.get("nodes", []):
    if node.get("id") == "17785930638200":
        # Only fix if dataset_ids is empty or missing
        dids = node.get("data", {}).get("dataset_ids", [])
        if not dids or dids == []:
            # Try to find a working dataset from the Meta Routing config
            import yaml
            try:
                with open("config/RMAP Chatbot Meta Routing.yml") as f:
                    mr = yaml.safe_load(f)
                for n in mr["workflow"]["graph"]["nodes"]:
                    if "Knowledge Retrieval" in n.get("data", {}).get("title", ""):
                        ref_dids = n["data"].get("dataset_ids", [])
                        if ref_dids:
                            node["data"]["dataset_ids"] = ref_dids
                            print(f"Set dataset_ids from Meta Routing: {ref_dids[0][:40]}...")
                            break
            except Exception as e:
                print(f"Could not read Meta Routing config: {e}")
        else:
            print(f"dataset_ids already set ({len(dids)} entries)")

payload = {
    "graph": graph,
    "features": draft.get("features", {}),
    "environment_variables": draft.get("environment_variables", []),
    "conversation_variables": draft.get("conversation_variables", []),
    "hash": draft.get("hash", ""),
}
with open(os.environ["TMP_PAYLOAD"], "w") as f:
    json.dump(payload, f)

print(f"Draft payload: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
PYEOF

# Post updated draft
HTTP=$(curl -sS -o "$TMP_RESP" -w "%{http_code}" -X POST "$DRAFT_URL" \
  -H "Cookie: ${DIFY_CONSOLE_COOKIE}" -H "x-csrf-token: ${DIFY_CSRF_TOKEN}" \
  -H "Content-Type: application/json" --data @"$TMP_PAYLOAD")

echo "Draft update HTTP: $HTTP"
"$PYTHON_BIN" -c "
import json
d = json.load(open('$TMP_RESP'))
if d.get('result') == 'success':
    print('Dataset fix applied ✓')
else:
    print('Fix may have failed:', json.dumps(d)[:200])
"
