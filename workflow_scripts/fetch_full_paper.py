# Code Node: Fetch Full Paper
# Node ID: 1778800001025

import json
import os
import traceback
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


def _safe_int(value, default=1):
    """Parse paper_count defensively. Never raises."""
    try:
        if value is None:
            return default
        s = str(value).strip()
        if not s:
            return default
        n = int(float(s))  # tolerates "3", "3.0", 3, 3.0
        return n if n > 0 else default
    except Exception:
        return default


def _core(
    doc_id=None,
    item_title=None,
    item_authors=None,
    item_year=None,
    item_journal=None,
    paper_count=None,
    api_url_input=None,
    api_key_input=None,
    dataset_id_input=None,
):
    # NOTE: Dify's code node runs in a sandboxed process that does NOT inherit
    # the app's .env variables via os.getenv() - only explicit node inputs are
    # visible. os.getenv("DIFY_DATASET_ID") / os.getenv("DIFY_API_KEY") will
    # almost always be empty in the sandbox even if .env is correct, which is
    # why api_key_input already existed as a fallback. dataset_id_input closes
    # the same gap for the dataset id. Map this node's "dataset_id_input"
    # input to your actual dataset id value in the Dify workflow UI (an app
    # environment variable reference, a Start-node input, or an upstream
    # node's output) - not to os.getenv.
    api_base = (
        _norm(api_url_input)
        or _norm(os.getenv("DIFY_API_URL"))
        or "http://rmap-chatbot-demo-dify/v1"
    ).rstrip("/")
    dataset_id = _norm(dataset_id_input) or _norm(os.getenv("DIFY_DATASET_ID")) or ""
    api_key = api_key_input or _norm(os.getenv("DIFY_API_KEY")) or ""

    if not dataset_id:
        return {
            "paper_context": "",
            "paper_fetch_error": (
                "dataset_id not configured. DEBUG - raw inputs received by this "
                f"code node: dataset_id_input={dataset_id_input!r} "
                f"(type={type(dataset_id_input).__name__}), "
                f"doc_id={doc_id!r}, item_title={item_title!r}, "
                f"os.getenv(DIFY_DATASET_ID)={os.getenv('DIFY_DATASET_ID')!r}. "
                "If dataset_id_input shows None here, the input variable name "
                "configured in this node's UI panel does not exactly match the "
                "function parameter name 'dataset_id_input' (Dify binds inputs "
                "by exact name) - open the node, check the Input Variables list, "
                "and confirm the variable name is exactly 'dataset_id_input'."
            ),
        }
    if not api_key:
        return {
            "paper_context": "",
            "paper_fetch_error": "DIFY_API_KEY not configured. Run import_dify_dsl.sh to inject from .env.",
        }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    resolved = _norm(doc_id)
    used_title_fallback = False
    if not resolved:
        title = _norm(item_title)
        if not title:
            # Both doc_id and item_title are empty/null - nothing to look up.
            return {
                "paper_context": "",
                "paper_fetch_error": (
                    "no doc_id and no title: upstream node did not pass either "
                    "'doc_id' or 'item_title' into this code node - check the "
                    "variable mapping on this node's inputs"
                ),
            }
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
    n = _safe_int(paper_count, default=1)
    # With MAX_PAPERS_FOR_SUMMARY=8: 8 papers × 6000 chars = 48K total
    # Fits in 65K context window with room for prompt (~13K) + output (~4K)
    chars_per_paper = max(4000, 48000 // n)
    context = f"{header}\n\n{text[:chars_per_paper]}"
    return {"paper_context": context, "paper_fetch_error": ""}


def main(
    doc_id=None,
    item_title=None,
    item_authors=None,
    item_year=None,
    item_journal=None,
    paper_count=None,
    api_url_input=None,
    api_key_input=None,
    dataset_id_input=None,
):
    """
    Top-level guard: no matter what happens inside _core (including bugs we
    haven't anticipated), this ALWAYS returns both declared output keys.
    Dify's "Output paper_context is missing" error happens when the node
    raises an uncaught exception and returns nothing at all - this wrapper
    makes that impossible.
    """
    try:
        result = _core(
            doc_id=doc_id,
            item_title=item_title,
            item_authors=item_authors,
            item_year=item_year,
            item_journal=item_journal,
            paper_count=paper_count,
            api_url_input=api_url_input,
            api_key_input=api_key_input,
            dataset_id_input=dataset_id_input,
        )
        # Defensive: guarantee both keys exist even if _core's logic changes later
        result.setdefault("paper_context", "")
        result.setdefault("paper_fetch_error", "")
        return result
    except Exception as exc:
        return {
            "paper_context": "",
            "paper_fetch_error": f"Unhandled exception: {exc}\n{traceback.format_exc()[:800]}",
        }