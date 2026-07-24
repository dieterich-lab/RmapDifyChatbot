#!/usr/bin/env python3
"""
Bulk-update Dify document metadata using PubMed (DOI → PMID → MEDLINE).

Usage:
    python scripts/update_dify_metadata.py [--dry-run]

Requires .env with DIFY_CONSOLE_EMAIL and DIFY_CONSOLE_PASSWORD_B64 for auto-login.
"""

import http.cookiejar
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dify_uploader.metadata import extract_metadata


def _console_login(base_url):
    """Login to Dify console, return (opener, csrf_token)."""
    login_file = REPO_ROOT / ".env"
    login_env = {}
    with open(login_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            login_env[k.strip()] = v.strip().strip('"')

    cj = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))

    data = json.dumps(
        {
            "email": login_env["DIFY_CONSOLE_EMAIL"],
            "password": login_env["DIFY_CONSOLE_PASSWORD_B64"],
            "language": "en-US",
            "remember_me": True,
        }
    ).encode()
    req = Request(
        f"{base_url}/console/api/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req) as resp:
        json.loads(resp.read())

    csrf = ""
    for c in cj:
        if "csrf" in c.name:
            csrf = c.value
    return opener, csrf


def _api_get(opener, csrf, url):
    req = Request(url, headers={"x-csrf-token": csrf})
    with opener.open(req) as resp:
        return json.loads(resp.read())


def _api_post(opener, csrf, url, body):
    data = json.dumps(body).encode()
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "x-csrf-token": csrf},
        method="POST",
    )
    with opener.open(req) as resp:
        return json.loads(resp.read()), resp.getcode()


def main():
    dry_run = "--dry-run" in sys.argv

    base = os.getenv("DIFY_BASE_URL", "http://rmap-chatbot-demo-dify")
    ds = os.getenv("DIFY_DATASET_ID", "5a231cec-21bf-40b9-86c8-87b9d01bca74")
    pdf_folder = os.getenv(
        "PDF_FOLDER", str(REPO_ROOT / "RMaP papers first funding period")
    )

    print("Logging in...")
    opener, csrf = _console_login(base)

    # ── Build PDF → path lookup ────────────────────────────────────
    pdf_map = {}
    for fn in os.listdir(pdf_folder):
        if fn.lower().endswith(".pdf"):
            pdf_map[fn.lower().replace(".pdf", "").strip()] = os.path.join(
                pdf_folder, fn
            )

    # ── Fetch all documents ────────────────────────────────────────
    print("Fetching documents...")
    all_docs = []
    for page in range(1, 5):
        url = f"{base}/console/api/datasets/{ds}/documents?page={page}&limit=50"
        data = _api_get(opener, csrf, url)
        items = data.get("data", [])
        if not items:
            break
        all_docs.extend(items)
        if len(items) < 50:
            break

    print(f"Found {len(all_docs)} documents")

    # ── Process each document ──────────────────────────────────────
    updates = []
    skipped = 0

    for i, doc in enumerate(all_docs):
        doc_id = doc["id"]
        doc_name = str(doc.get("name", "")).strip()

        # Match PDF
        clean = doc_name.lower().replace("__two_pass_", "").replace(".pdf", "")
        pdf_path = pdf_map.get(clean)
        if not pdf_path:
            for key, path in pdf_map.items():
                if clean[:40] in key or key[:40] in clean:
                    pdf_path = path
                    break

        if not pdf_path:
            skipped += 1
            continue

        # Extract new metadata via PubMed
        meta = extract_metadata(os.path.basename(pdf_path), pdf_path)
        new_title = meta.get("title", "")
        if not new_title or not meta.get("pmid"):
            skipped += 1
            continue

        # Get current metadata IDs from doc (already in list response)
        # We need full detail for metadata IDs
        detail_url = f"{base}/console/api/datasets/{ds}/documents/{doc_id}"
        detail = _api_get(opener, csrf, detail_url)

        meta_map = {
            m["name"]: m["id"] for m in detail.get("doc_metadata", []) if m.get("id")
        }

        new_values = {
            "title": new_title,
            "authors": meta.get("authors", "Unknown"),
            "year": meta.get("year", "Unknown"),
            "journal": meta.get("journal", "Unknown"),
        }

        # Check if update is needed
        old_title = ""
        for m in detail.get("doc_metadata", []):
            if m.get("name") == "title":
                old_title = m.get("value", "")
        if new_title == old_title:
            skipped += 1
            continue

        metadata_list = []
        for name, value in new_values.items():
            if name in meta_map:
                metadata_list.append(
                    {
                        "id": meta_map[name],
                        "name": name,
                        "type": "string",
                        "value": value,
                    }
                )

        if dry_run:
            print(f"[{i+1}/{len(all_docs)}] 🔍 {doc_name[:60]}")
            print(f"    {old_title[:70]} → {new_title[:70]}")
            updates.append({"doc_id": doc_id, "metadata_list": metadata_list})
        else:
            updates.append({"doc_id": doc_id, "metadata_list": metadata_list})
            # Batch update in groups of 10
            if len(updates) >= 10 or i == len(all_docs) - 1:
                batch = {
                    "operation_data": [
                        {
                            "document_id": u["doc_id"],
                            "metadata_list": u["metadata_list"],
                        }
                        for u in updates
                    ]
                }
                url = f"{base}/console/api/datasets/{ds}/documents/metadata"
                result, code = _api_post(opener, csrf, url, batch)
                if code == 200:
                    print(f"  ✅ Batch: {len(updates)} docs updated")
                else:
                    print(f"  ❌ Batch failed: HTTP {code}")
                updates = []
                time.sleep(1)

    print(f"\nDone: {len(all_docs) - skipped} would update, {skipped} skipped")


if __name__ == "__main__":
    main()
