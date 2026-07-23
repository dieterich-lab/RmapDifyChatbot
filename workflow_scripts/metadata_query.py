# Code Node: Metadata Query
# Node ID: 17786780698570

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CODE_VERSION = "metadata_query_v2026-07-15_broad-query-fix"

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

    # Normalize "Last, First" → "First Last"
    if "," in text:
        comma_parts = [p.strip() for p in text.split(",", 1)]
        if len(comma_parts) == 2 and comma_parts[0] and comma_parts[1]:
            variants.append(f"{comma_parts[1]} {comma_parts[0]}")

    parts = text.split(" ")
    if len(parts) >= 2:
        first = parts[0].strip(".,;")
        last = parts[-1].strip(".,;")
        if first and last:
            variants.append(f"{first[0]}. {last}")
            variants.append(f"{first[0]} {last}")
            variants.append(last)

    # Always add just the last word as a variant (handles "Dieterich", "Helm" etc.)
    if parts:
        last_word = parts[-1].strip(".,;")
        if last_word and last_word.lower() not in {v.lower() for v in variants}:
            variants.append(last_word)

    seen = set()
    deduped = []
    for item in variants:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # Umlaut normalization: add both ö→oe AND ö→o variants
    # PubMed strips umlauts (ö→o), German expansion uses oe (ö→oe)
    umlaut_expand = str.maketrans(
        {"ö": "oe", "ü": "ue", "ä": "ae", "ß": "ss", "Ö": "Oe", "Ü": "Ue", "Ä": "Ae"}
    )
    umlaut_strip = str.maketrans(
        {"ö": "o", "ü": "u", "ä": "a", "ß": "ss", "Ö": "O", "Ü": "U", "Ä": "A"}
    )
    extra = []
    for item in deduped:
        expanded = item.translate(umlaut_expand)
        if expanded.lower() not in seen:
            extra.append(expanded)
        stripped = item.translate(umlaut_strip)
        if stripped.lower() not in seen and stripped.lower() != expanded.lower():
            extra.append(stripped)
    deduped.extend(extra)

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

    # Multi-author OR matching: if any input contains commas, split and OR-match
    has_multi = any("," in a for a in author_inputs)
    if has_multi:
        all_names = []
        for a in author_inputs:
            for part in a.split(","):
                part = part.strip()
                if part:
                    all_names.append(part)
        # Paper matches if ANY of the comma-separated names match
        for name in all_names:
            variants = [v.lower() for v in _author_variants(name)]
            if any(v in meta_authors.lower() for v in variants):
                break  # matched this name
            last_name = name.strip().split()[-1].strip(".,;").lower()
            if last_name and last_name in meta_authors.lower():
                break  # matched via last name
        else:
            return False  # no name matched
    else:
        # Single-author: all must match (AND logic, typically just one)
        for author in author_inputs:
            variants = [v.lower() for v in _author_variants(author)]
            if not any(v in meta_authors.lower() for v in variants):
                # Last resort: extract just the last name and check again.
                # Handles "Chr. Dieterich" vs "Christoph Dieterich" where
                # the first name abbreviation doesn't match.
                last_name = author.strip().split()[-1].strip(".,;").lower()
                if not last_name or last_name not in meta_authors.lower():
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


def _render_result(
    matches: list[dict], total_docs: int, is_multi_author: bool = False
) -> str:
    MAX_RESULTS = 30  # Dify array output limit
    if not matches:
        return (
            "Keine Dokumente gefunden.\n"
            "Tipps:\n"
            "- Autor:innen-Namen ausschreiben (z.B. 'Christoph Dieterich')\n"
            "- Nachname allein reicht oft (z.B. 'Dieterich')\n"
            "- Jahr als vierstellige Zahl angeben (z.B. '2024')\n"
            f"Code-Version: {CODE_VERSION}; Dokumente geprueft: {total_docs}; Treffer: 0"
        )

    truncated = len(matches) > MAX_RESULTS
    display_docs = matches[:MAX_RESULTS] if truncated else matches

    # For multi-author queries: pre-format the output to look like LLM output,
    # so the downstream Metadata LLM just passes it through verbatim.
    if is_multi_author:
        lines = [f"{len(matches)} papers", ""]
        for idx, doc in enumerate(matches, start=1):
            lines.append(f"{idx}. **{doc['title']}**")
            if doc.get("authors"):
                lines.append(f"   - Authors: {doc['authors']}")
            if doc.get("year"):
                lines.append(f"   - Year: {doc['year']}")
            if doc.get("journal"):
                lines.append(f"   - Journal: {doc['journal']}")
            lines.append("")
        # No cap for multi-author: the Metadata LLM is bypassed, so no context limit.
        # Final Answer Sanitizer passes result_text through verbatim.
        if len(matches) > MAX_RESULTS:
            lines.append(
                f"(Showing all {len(matches)} results. "
                "Refine your query with additional filters for a narrower list.)"
            )
        return "\n".join(lines)

    # Standard format for single-author / non-multi queries
    lines = []
    for idx, doc in enumerate(display_docs, start=1):
        lines.append(
            f"{idx}. {doc['title']} | {doc['authors']} | {doc['year']} | {doc['journal']} | {doc.get('id', '')}"
        )
    header = (
        f"Code-Version: {CODE_VERSION}; Dokumente geprueft: {total_docs}; "
        f"Treffer: {len(matches)}"
    )
    result = header + "\n" + "\n".join(lines)
    if truncated:
        result += (
            f"\n\n(Es werden nur die ersten {MAX_RESULTS} von {len(matches)} Ergebnissen angezeigt. "
            "Bitte die Suche mit einem Autor:innen-Namen, Jahr oder Journal einschränken.)"
        )
    return result


def main(
    year=None,
    authors=None,
    journal=None,
    title=None,
    paper_list=None,
    list_mode=None,
    api_key_input=None,
    dataset_id_input=None,
):
    api_base = (os.getenv("DIFY_API_URL") or "http://rmap-chatbot-demo-dify/v1").rstrip(
        "/"
    )
    dataset_id = os.getenv("DIFY_DATASET_ID") or "<your-dataset-id>"
    api_key = os.getenv("DIFY_API_KEY") or api_key_input or ""

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
            if not _is_set(year):
                year = first.get("year", "")
            if not _is_set(journal):
                journal = first.get("journal", "")
            if not _is_set(title):
                title = first.get("title", "")
        # Collect authors from ALL entries (supports multi-name OR queries
        # where parse_router_output splits "X, Y" into separate entries)
        if not _is_set(authors):
            all_authors = []
            for entry in paper_list:
                if isinstance(entry, dict):
                    a = (entry.get("authors") or "").strip()
                    if a:
                        all_authors.append(a)
            if all_authors:
                authors = ", ".join(all_authors)

    headers = _build_headers(str(api_key).strip())
    docs, errors = _collect_documents(str(api_base), str(dataset_id).strip(), headers)

    year_filter = _sanitize_year_filter(year)
    journal_filter = _sanitize_free_text_filter(journal, max_len=80)
    title_filter = _sanitize_free_text_filter(title, max_len=160)

    has_any_filter = any(
        [
            _is_set(year_filter),
            _is_set(journal_filter),
            _is_set(title_filter),
            _is_set(authors),
        ]
    )

    # No-filter query → return all documents or distinct authors
    if not has_any_filter:
        if str(list_mode or "").strip().lower() == "authors":
            # Extract distinct authors from all docs
            author_set = set()
            for d in docs:
                for a in d.get("authors", "").split(","):
                    a = a.strip()
                    if a and len(a) > 2:
                        author_set.add(a)
            author_list = sorted(author_set)
            total = len(author_list)
            display = author_list[:100]
            lines = [f"{i}. {a}" for i, a in enumerate(display, 1)]
            text = f"Distinct authors in dataset: {total}\n\n" + "\n".join(lines)
            if total > 100:
                text += f"\n\n(Showing first 100 of {total} authors. Use 'Papers by <name>' to find specific authors.)"
            return {
                "result": text.split("\n")[:30],
                "result_text": text,
            }
        else:
            uniq = {}
            for d in docs:
                k = (
                    d.get("title", "").strip().lower(),
                    d.get("authors", "").strip().lower(),
                    d.get("year", "").strip(),
                    d.get("journal", "").strip().lower(),
                )
                if k not in uniq:
                    uniq[k] = d
            all_docs = list(uniq.values())
            total = len(all_docs)
            lines = [
                f"{i}. {d['title']}, {d['year']}, {d['journal']}"
                for i, d in enumerate(all_docs, 1)
            ]
            text = f"Total papers in dataset: {total}\n\n" + "\n".join(lines)
            return {
                "result": text.split("\n")[:30],
                "result_text": text,
            }

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

    # Detect multi-author OR query for result header hint
    is_multi = "," in str(authors or "")

    result_text = _render_result(
        final_docs, total_docs=len(docs), is_multi_author=is_multi
    )
    if errors:
        result_text += "\nFehlerdetails:\n" + "\n".join(f"- {e}" for e in errors[:8])
    # Cap result array at 30 elements (Dify limit); split only display lines
    result_lines = result_text.split("\n") if result_text else []
    if len(result_lines) > 30:
        result_lines = result_lines[:30]
    return {
        "result": result_lines,
        "result_text": result_text,
    }
