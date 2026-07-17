# Code Node: Fetch Full Paper
# Node ID: 1778800001025

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _norm(text):
    return str(text or "").strip()


def _run_json_get(url, headers, timeout=30):
    req = Request(url=url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {}, f"HTTPError {exc.code}: {body}"
    except URLError as exc:
        return {}, f"URLError: {exc}"
    except Exception as exc:
        return {}, f"Error: {exc}"
    if status != 200:
        return {}, f"HTTP {status}: {body}"
    try:
        return json.loads(body), None
    except Exception:
        return {}, f"Invalid JSON: {body[:400]}"


def _fetch_all_segments(api_base, dataset_id, doc_id, headers):
    all_segs = []
    seen = set()
    for page in range(1, 31):
        q = urlencode({"page": page, "limit": 100})
        url = f"{api_base}/datasets/{dataset_id}/documents/{doc_id}/segments?{q}"
        payload, err = _run_json_get(url, headers=headers, timeout=30)
        if err:
            if page == 1:
                return "", f"segments error: {err}"
            break
        items = payload.get("data") or payload.get("segments") or []
        if not items:
            break
        for seg in items:
            for key in ("content", "text"):
                val = seg.get(key)
                if isinstance(val, str) and val.strip():
                    sid = _norm(seg.get("id")) or val[:100]
                    if sid not in seen:
                        seen.add(sid)
                        pos = seg.get("position", 10**9)
                        all_segs.append((pos, val.strip()))
                    break
        if len(items) < 100:
            break
    if not all_segs:
        return "", "no segments found"
    all_segs.sort(key=lambda x: x[0])
    return "\n\n".join(t for _, t in all_segs), None


def _find_doc_id_by_title(api_base, dataset_id, title, headers):
    # Find document ID by matching title against doc_metadata from the list response.
    # Uses the list endpoint doc_metadata field directly - no per-document detail calls.
    expected = title.lower().strip()
    exp_words = set(expected.split())
    for page in range(1, 21):
        q = urlencode({"page": page, "limit": 100})
        url = f"{api_base}/datasets/{dataset_id}/documents?{q}"
        payload, err = _run_json_get(url, headers=headers, timeout=30)
        if err:
            break
        items = payload.get("data") or []
        if not items:
            break
        for item in items:
            doc_id = _norm(item.get("id"))
            if not doc_id:
                continue
            # Read title from doc_metadata (already in list response, no extra call)
            doc_title = ""
            for m in item.get("doc_metadata") or []:
                if _norm((m or {}).get("name")).lower() == "title":
                    doc_title = _norm((m or {}).get("value"))
                    break
            if not doc_title:
                doc_title = _norm(item.get("name", ""))
            if not doc_title:
                continue
            if doc_title.lower() == expected:
                return doc_id, None
            if exp_words:
                doc_words = set(doc_title.lower().split())
                if len(exp_words & doc_words) / len(exp_words) >= 0.8:
                    return doc_id, None
        if len(items) < 100:
            break
    return "", f"no document found for title: {title!r}"


def main(
    doc_id=None,
    item_title=None,
    item_authors=None,
    item_year=None,
    item_journal=None,
    paper_count=None,
    api_key_input=None,
):
    api_base = (
        _norm(os.getenv("DIFY_API_URL")) or "http://rmap-chatbot-demo-dify/v1"
    ).rstrip("/")
    dataset_id = (
        _norm(os.getenv("DIFY_DATASET_ID")) or "<your-dataset-id>"
    )
    api_key = _norm(os.getenv("DIFY_API_KEY")) or api_key_input or ""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    resolved = _norm(doc_id)
    used_title_fallback = False
    if not resolved:
        title = _norm(item_title)
        if not title:
            return {"paper_context": "", "paper_fetch_error": "no doc_id and no title"}
        resolved, err = _find_doc_id_by_title(api_base, dataset_id, title, headers)
        if not resolved:
            return {
                "paper_context": "",
                "paper_fetch_error": err or "title lookup failed",
            }
        used_title_fallback = True

    text, err = _fetch_all_segments(api_base, dataset_id, resolved, headers)

    # Fallback: if doc_id fetch returned no segments, try title lookup
    if (not text or err) and not used_title_fallback:
        title = _norm(item_title)
        if title:
            fallback_id, fb_err = _find_doc_id_by_title(
                api_base, dataset_id, title, headers
            )
            if fallback_id and fallback_id != resolved:
                text2, err2 = _fetch_all_segments(
                    api_base, dataset_id, fallback_id, headers
                )
                if text2:
                    text, err = text2, None

    if err:
        return {"paper_context": "", "paper_fetch_error": err}

    title = _norm(item_title)
    year = _norm(item_year)
    journal = _norm(item_journal)
    authors = _norm(item_authors)
    meta_line = (
        f"{title} ({year}, {journal}) — {authors}"
        if (year or journal or authors)
        else title
    )
    header = f"=== {meta_line} ==="
    n = int(paper_count) if paper_count and int(paper_count) > 0 else 1
    chars_per_paper = max(4000, 48000 // n)
    context = f"{header}\n\n{text[:chars_per_paper]}"
    return {"paper_context": context, "paper_fetch_error": ""}
