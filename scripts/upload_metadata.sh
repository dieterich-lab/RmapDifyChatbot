#!/usr/bin/env bash
#SBATCH --job-name=rmap_meta_upload
#SBATCH --output=logs/slurm/rmap_meta_upload_%j.out
#SBATCH --partition=medium
#SBATCH --mem=2G

set -euo pipefail
#
# Upload metadata from a JSON dump to the parent-child dataset.
# Matches documents by filename, then patches title/authors/year/journal.
#
# Usage:
#   sbatch scripts/upload_metadata.sh [metadata_dump.json]
#   (or run directly: bash scripts/upload_metadata.sh [metadata_dump.json])
#
# SLURM: submit with --dependency=afterok:<extract_job_id>
#   sbatch --dependency=afterok:668391 scripts/upload_metadata.sh
#
# Requires: DIFY_BASE_URL, DIFY_DATASET_API_KEY in environment or defaults.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
METADATA_FILE="${1:-$REPO_ROOT/reports/metadata_dump_$(date '+%Y-%m-%d').json}"
DATASET_ID="${DATASET_ID:-65b46261-2c5e-48e9-8de4-3ca0785281e3}"
DIFY_BASE_URL="${DIFY_BASE_URL:-http://rmap-chatbot-demo-dify}"
DIFY_DATASET_API_KEY="${DIFY_DATASET_API_KEY:-REDACTED}"

cd "$REPO_ROOT"

if [[ ! -f "$METADATA_FILE" ]]; then
  echo "ERROR: Metadata file not found: $METADATA_FILE"
  exit 1
fi

echo "===== METADATA UPLOAD ====="
echo "dataset=$DATASET_ID"
echo "metadata_file=$METADATA_FILE"
echo "api_base=$DIFY_BASE_URL"

DIFY_BASE_URL="$DIFY_BASE_URL" \
DATASET_ID="$DATASET_ID" \
DIFY_DATASET_API_KEY="$DIFY_DATASET_API_KEY" \
"$REPO_ROOT/.venv/bin/python" -c '
import json, os, sys, time, requests

API_BASE = os.environ["DIFY_BASE_URL"].rstrip("/")
DS_ID = os.environ["DATASET_ID"]
API_KEY = os.environ["DIFY_DATASET_API_KEY"]
META_FILE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("METADATA_FILE", "")

H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ── Load metadata dump ──────────────────────────────────────────────
with open(META_FILE, encoding="utf-8") as f:
    dump = json.load(f)

entries = dump.get("results", [])
print(f"Loaded {len(entries)} metadata entries")

# ── Fetch all documents from dataset ────────────────────────────────
print("Fetching document list...")
all_docs = []
for page in range(1, 30):
    r = requests.get(f"{API_BASE}/v1/datasets/{DS_ID}/documents?page={page}&limit=100",
                     headers=H, timeout=60)
    if r.status_code != 200:
        break
    data = r.json().get("data", [])
    if not data:
        break
    all_docs.extend(data)
    if len(data) < 100:
        break

# Build filename → doc_id map
fn_to_doc = {}
for doc in all_docs:
    name = doc.get("name", "")
    if name:
        fn_to_doc[name] = doc.get("id")

print(f"  Found {len(all_docs)} documents, {len(fn_to_doc)} with names")

# ── Ensure metadata fields exist ─────────────────────────────────────
print("Ensuring metadata fields...")
field_names = ["title", "authors", "year", "journal"]
existing_fields = {}

r = requests.get(f"{API_BASE}/v1/datasets/{DS_ID}/metadata", headers=H, timeout=60)
if r.status_code == 200:
    for item in (r.json() if isinstance(r.json(), list) else r.json().get("data", [])):
        name = item.get("name", "")
        fid = item.get("id", "")
        if name and fid:
            existing_fields[name] = fid

for fname in field_names:
    if fname not in existing_fields:
        r2 = requests.post(f"{API_BASE}/v1/datasets/{DS_ID}/metadata",
                           headers=H, json={"name": fname, "type": "string"}, timeout=60)
        if r2.status_code in (200, 201):
            fid = r2.json().get("id", "")
            existing_fields[fname] = fid
            print(f"  Created field: {fname} ({fid})")
        else:
            print(f"  WARN: Could not create field {fname}: {r2.status_code} {r2.text[:200]}")

print(f"  Fields ready: {list(existing_fields.keys())}")

# ── Match and upload ─────────────────────────────────────────────────
uploaded = 0
skipped_no_match = 0
skipped_no_fields = 0
errors = []

for i, entry in enumerate(entries):
    fn = entry.get("_filename", "")
    title = entry.get("title", "")
    authors = entry.get("authors", "")
    year = entry.get("year", "")
    journal = entry.get("journal", "")

    doc_id = fn_to_doc.get(fn)
    if not doc_id:
        skipped_no_match += 1
        if skipped_no_match <= 5:
            print(f"  SKIP (no match): {fn}")
        continue

    # Build metadata payload (only fields that exist)
    meta_items = []
    for fname, fval in [("title", title), ("authors", authors),
                         ("year", year), ("journal", journal)]:
        fid = existing_fields.get(fname)
        if fid and fval and str(fval).strip():
            meta_items.append({"id": fid, "name": fname, "value": str(fval).strip()})

    if not meta_items:
        skipped_no_fields += 1
        continue

    payload = {
        "operation_data": [{
            "document_id": doc_id,
            "partial_update": True,
            "metadata_list": meta_items,
        }]
    }

    r = requests.post(f"{API_BASE}/v1/datasets/{DS_ID}/documents/metadata",
                      headers=H, json=payload, timeout=60)
    if r.status_code == 200:
        uploaded += 1
        if uploaded % 10 == 0:
            print(f"  [{uploaded}/{len(entries)}] OK: {fn[:60]}")
    else:
        errors.append({"filename": fn, "status": r.status_code, "response": r.text[:200]})
        print(f"  FAIL ({r.status_code}): {fn[:60]} — {r.text[:150]}")

    time.sleep(0.2)  # gentle rate limit

# ── Summary ──────────────────────────────────────────────────────────
print(f"\n===== RESULT =====")
print(f"Total entries:    {len(entries)}")
print(f"Uploaded:         {uploaded}")
print(f"No doc match:     {skipped_no_match}")
print(f"No fields:        {skipped_no_fields}")
print(f"Errors:           {len(errors)}")
if errors:
    for e in errors[:10]:
        print(f"  - {e['filename']}: HTTP {e['status']}")
' "$METADATA_FILE"
