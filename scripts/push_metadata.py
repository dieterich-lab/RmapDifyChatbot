#!/usr/bin/env python3
"""Push metadata from a JSON dump to the Dify dataset."""

import json
import os
import re
import sys
import time

import requests

API_BASE = os.getenv("DIFY_BASE_URL", "http://rmap-chatbot-demo-dify").rstrip("/")
DS_ID = os.getenv("DIFY_DATASET_ID", "<your-dataset-id>")

# Read API key from .env
env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
with open(env_file) as f:
    for line in f:
        line = line.strip()
        if line.startswith("DIFY_DATASET_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip().strip('"')
            break
    else:
        print("ERROR: DIFY_DATASET_API_KEY not found in .env")
        sys.exit(1)

H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Load metadata
dump_file = sys.argv[1] if len(sys.argv) > 1 else "reports/metadata_dump_32b.json"
print(f"Loading: {dump_file}")
with open(dump_file) as f:
    dump = json.load(f)

# Fetch all Dify documents
print("Fetching Dify documents...")
all_docs = []
for page in range(1, 10):
    url = f"{API_BASE}/v1/datasets/{DS_ID}/documents?page={page}&limit=100"
    r = requests.get(url, headers=H, timeout=60)
    if r.status_code != 200:
        print(f"  API error: {r.status_code}")
        break
    data = r.json().get("data", [])
    if not data:
        break
    all_docs.extend(data)
    print(f"  Page {page}: {len(data)} docs")

print(f"Total Dify docs: {len(all_docs)}")


# Build lookup: clean name -> doc_id
def clean_name(name):
    n = name.replace(".pdf", "").strip()
    n = re.sub(r"__two_pass_\d+", "", n)
    return n.strip()


name_to_id = {}
for doc in all_docs:
    name_to_id[clean_name(doc.get("name", ""))] = doc.get("id")

# Get metadata field IDs
print("Fetching metadata field IDs...")
r = requests.get(f"{API_BASE}/v1/datasets/{DS_ID}/metadata", headers=H, timeout=60)
field_name_to_id = {}
if r.status_code == 200:
    raw = r.json()
    # Response can be a list or {"doc_metadata": [...]}
    items = (
        raw if isinstance(raw, list) else raw.get("doc_metadata", raw.get("data", []))
    )
    for item in items:
        n = item.get("name")
        fid = item.get("id")
        if n and fid:
            field_name_to_id[n] = fid
print(f"  Fields: {list(field_name_to_id.keys())}")

# Match and build updates
updates = []
unmatched = []
for entry in dump["results"]:
    pdf_name = entry.get("_filename", "").replace(".pdf", "").strip()
    doc_id = name_to_id.get(pdf_name)
    if not doc_id:
        unmatched.append(pdf_name)
        continue

    meta_items = []
    for fname in ["title", "authors", "year", "journal"]:
        val = entry.get(fname, "")
        fid = field_name_to_id.get(fname)
        if val and str(val).strip() and fid:
            meta_items.append({"id": fid, "name": fname, "value": str(val).strip()})

    if meta_items:
        updates.append({"document_id": doc_id, "metadata_list": meta_items})

print(f"Matched: {len(updates)}, Unmatched: {len(unmatched)}")
for u in unmatched:
    print(f"  UNMATCHED: {u}")

if not updates:
    print("Nothing to push!")
    sys.exit(0)

# Push in batches
print(f"Pushing {len(updates)} documents...")
pushed = 0
failed = 0
for i in range(0, len(updates), 10):
    batch = updates[i : i + 10]
    payload = {
        "operation_data": [
            {
                "document_id": u["document_id"],
                "partial_update": True,
                "metadata_list": u["metadata_list"],
            }
            for u in batch
        ]
    }
    url = f"{API_BASE}/v1/datasets/{DS_ID}/documents/metadata"
    r = requests.post(url, headers=H, json=payload, timeout=60)
    if r.status_code == 200:
        pushed += len(batch)
    else:
        failed += len(batch)
        print(f"  Batch {i // 10 + 1}: FAILED {r.status_code}")
    time.sleep(0.3)

print(f"\nDone! Pushed {pushed}, Failed {failed}")
