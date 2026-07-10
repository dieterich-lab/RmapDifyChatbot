# Code Node: Metadata Query
# Node ID: 17786780698570

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CODE_VERSION = "metadata_query_v2026-05-11_dify-metadata_1"

_EMPTY_TOKENS = {
    "",
    "null",
    "none",
    "unknown",
    "n/a",
    "na",
    "[]",
    "{}",
    "-",
}


def _is_set(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    if isinstance(value, list):
        return any(_is_set(item) for item in value)
    if isinstance(value, dict):
        return any(_is_set(v) for v in value.values())
    text = str(value).strip()
    return text.lower() not in _EMPTY_TOKENS


def _normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in _EMPTY_TOKENS else text


def _to_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_normalize_text(v) for v in value if _is_set(v)]
    if isinstance(value, dict):
        candidates = []
        for key in ("value", "name", "author", "authors", "text"):
            if key in value:
                entry = value.get(key)
                if isinstance(entry, list):
                    candidates.extend(_to_string_list(entry))
                elif _is_set(entry):
                    norm = _normalize_text(entry)
                    if norm:
                        candidates.append(norm)
        if candidates:
            return candidates
        return [_normalize_text(v) for v in value.values() if _is_set(v)]
    if _is_set(value):
        normalized = _normalize_text(value)
        return [normalized] if normalized else []
    return []


def _author_variants(author: str) -> list[str]:
    text = " ".join(str(author).strip().split())
    if not text:
        return []

    variants = [text]
    parts = text.split(" ")
    if len(parts) >= 2:
        first = parts[0].strip(".")
        last = parts[-1].strip(".,;")
        if first and last:
            variants.append(f"{first[0]}. {last}")
            variants.append(f"{first[0]} {last}")
            variants.append(last)

    seen = set()
    deduped = []
    for item in variants:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _run_json_get(
    url: str, headers: dict, timeout: int = 30
) -> tuple[dict, str | None]:
    request = Request(url=url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.getcode()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {}, f"Dify API Error {exc.code}: {body}"
    except URLError as exc:
        return {}, f"Verbindungsfehler zur Dify API: {exc}"
    except Exception as exc:
        return {}, f"Unbekannter Dify API-Fehler: {exc}"

    if status != 200:
        return {}, f"Dify API Error {status}: {body}"

    try:
        return json.loads(body), None
    except ValueError:
        return {}, f"Ungueltige JSON-Antwort: {body}"


def _extract_items(payload: dict) -> list[dict]:
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload.get("data", [])
        if isinstance(payload.get("documents"), list):
            return payload.get("documents", [])
    return []


def _metadata_to_dict(detail: dict) -> dict[str, str]:
    result = {}
    for item in detail.get("doc_metadata", []) or []:
        name = str((item or {}).get("name") or "").strip().lower()
        value = (item or {}).get("value")
        if name:
            result[name] = "" if value is None else str(value).strip()
    return result


def _matches_filters(meta: dict[str, str], year, authors, journal, title) -> bool:
    meta_year = _normalize_text(meta.get("year", ""))
    meta_authors = _normalize_text(meta.get("authors", ""))
    meta_journal = _normalize_text(meta.get("journal", ""))
    meta_title = _normalize_text(meta.get("title", ""))

    year_text = _normalize_text(year)
    journal_text = _normalize_text(journal)
    title_text = _normalize_text(title)

    if _is_set(year_text) and year_text.lower() != meta_year.lower():
        return False

    if _is_set(journal_text) and journal_text.lower() not in meta_journal.lower():
        return False

    if _is_set(title_text) and title_text.lower() not in meta_title.lower():
        return False

    author_inputs = _to_string_list(authors)
    for author in author_inputs:
        variants = [v.lower() for v in _author_variants(author)]
        if not any(v in meta_authors.lower() for v in variants):
            return False

    return True


def _sanitize_year_filter(value) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    return text if re.fullmatch(r"(19|20)\d{2}", text) else ""


def _sanitize_free_text_filter(value, max_len: int = 120) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    if len(text) > max_len:
        return ""
    if "?" in text:
        return ""
    lower = text.lower()
    noisy_markers = ["which documents", "co-authored", "co-authored by", "authored by"]
    if any(marker in lower for marker in noisy_markers):
        return ""
    return text


def _collect_documents(
    api_base: str, dataset_id: str, headers: dict
) -> tuple[list[dict], list[str]]:
    errors = []
    docs = []

    all_items = []
    for page in range(1, 21):
        q = urlencode({"page": page, "limit": 100})
        list_url = f"{api_base}/datasets/{dataset_id}/documents?{q}"
        payload, err = _run_json_get(list_url, headers=headers)
        if err:
            if page == 1:
                return [], [err]
            break

        items = _extract_items(payload)
        if not items:
            break
        all_items.extend(items)
        if len(items) < 100:
            break

    for item in all_items:
        doc_id = str((item or {}).get("id") or "").strip()
        if not doc_id:
            continue

        detail_url = f"{api_base}/datasets/{dataset_id}/documents/{doc_id}?{urlencode({'metadata': 'all'})}"
        detail, detail_err = _run_json_get(detail_url, headers=headers)
        if detail_err:
            errors.append(f"Dokument {doc_id}: {detail_err}")
            continue

        meta = _metadata_to_dict(detail)
        docs.append(
            {
                "id": doc_id,
                "title": meta.get("title") or str(detail.get("name") or "").strip(),
                "authors": meta.get("authors", ""),
                "year": meta.get("year", ""),
                "journal": meta.get("journal", ""),
            }
        )

    return docs, errors


def _render_result(matches: list[dict], total_docs: int) -> str:
    if not matches:
        return (
            "Keine Dokumente gefunden.\n"
            f"Code-Version: {CODE_VERSION}; Dokumente geprueft: {total_docs}; Treffer: 0"
        )

    lines = []
    for idx, doc in enumerate(matches, start=1):
        lines.append(
            f"{idx}. {doc['title']} | {doc['authors']} | {doc['year']} | {doc['journal']} | {doc.get('id', '')}"
        )
    header = (
        f"Code-Version: {CODE_VERSION}; Dokumente geprueft: {total_docs}; "
        f"Treffer: {len(matches)}"
    )
    return header + "\n" + "\n".join(lines)


def main(year=None, authors=None, journal=None, title=None, paper_list=None):
    api_base = (os.getenv("DIFY_API_URL") or "http://rmap-chatbot-demo-dify/v1").rstrip(
        "/"
    )
    dataset_id = os.getenv("DIFY_DATASET_ID") or "<your-dataset-id>"
    api_key = os.getenv("DIFY_API_KEY") or "REDACTED"

    if not _is_set(api_base) or not _is_set(dataset_id) or not _is_set(api_key):
        return {
            "result": (
                "Dify API Konfiguration unvollstaendig. "
                "Erwarte DIFY_API_URL, DIFY_DATASET_ID und DIFY_API_KEY."
            )
        }

    # Extract filter values from paper_list if passed (Parse Router Output)
    if isinstance(paper_list, list) and len(paper_list) > 0:
        first = paper_list[0]
        if isinstance(first, dict):
            if not _is_set(authors):
                authors = first.get("authors", "")
            if not _is_set(year):
                year = first.get("year", "")
            if not _is_set(journal):
                journal = first.get("journal", "")
            if not _is_set(title):
                title = first.get("title", "")

    headers = _build_headers(str(api_key).strip())
    docs, errors = _collect_documents(str(api_base), str(dataset_id).strip(), headers)

    year_filter = _sanitize_year_filter(year)
    journal_filter = _sanitize_free_text_filter(journal, max_len=80)
    title_filter = _sanitize_free_text_filter(title, max_len=160)

    matches = []
    for doc in docs:
        if _matches_filters(doc, year_filter, authors, journal_filter, title_filter):
            matches.append(doc)

    unique = {}
    for doc in matches:
        key = (
            (doc.get("title") or "").strip().lower(),
            (doc.get("authors") or "").strip().lower(),
            (doc.get("year") or "").strip(),
            (doc.get("journal") or "").strip().lower(),
        )
        if key not in unique:
            unique[key] = doc
    final_docs = list(unique.values())

    result_text = _render_result(final_docs, total_docs=len(docs))
    if errors:
        result_text += "\nFehlerdetails:\n" + "\n".join(f"- {e}" for e in errors[:8])
    return {
        "result": (result_text.split("\n") if result_text else []),
        "result_text": result_text,
    }
