import json
import re

NL = chr(10)


def _extract_text(chunk):
    """Extract text content from a retrieval chunk (handles multiple formats)."""
    if isinstance(chunk, dict):
        seg = chunk.get("segment", {})
        if isinstance(seg, dict) and seg.get("content", "").strip():
            return str(seg["content"]).strip()
        if chunk.get("content", "").strip():
            return str(chunk["content"]).strip()
        ccs = chunk.get("child_chunks", [])
        if ccs:
            parts = [
                str(c.get("content", "")).strip()
                for c in ccs if isinstance(c, dict)
            ]
            return NL.join(p for p in parts if p)
        return ""

    text = str(chunk or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return _extract_text(obj)
            if isinstance(obj, list):
                parts = [_extract_text(i) for i in obj[:3]]
                return NL.join(p for p in parts if p)
        except Exception:
            pass
    return text


def _is_reference_chunk(text):
    """Detect bibliography/reference list chunks using scoring heuristics."""
    t = str(text or "").strip()
    if not t or len(t) < 20:
        return False

    doi_count = len(re.findall(r"doi\.org/\S+|DOI:\s*\S+", t, re.IGNORECASE))
    numbered_refs = len(re.findall(
        r"(?:^|" + NL + r")\s*(?:\d+\.[ \t]|\[\d+\][ \t]|\(\d+\)\s)", t
    ))
    paren_refs_anywhere = len(re.findall(r"\(\d+\)\s", t))
    etal_count = len(re.findall(r"\bet\s+al\b", t, re.IGNORECASE))
    year_parens = len(re.findall(r"\((?:19|20)\d{2}[a-z]?\)", t))

    score = (
        doi_count * 3.0
        + numbered_refs * 1.5
        + paren_refs_anywhere * 1.0
        + etal_count * 0.5
        + year_parens * 0.3
    )
    density = score / max(1.0, len(t) / 500.0)

    if doi_count >= 4:
        return True
    if numbered_refs >= 8:
        return True
    if density > 1.8:
        return True

    first_line = t.split(NL)[0].strip()
    if (re.match(r"^\d+[\.,]\s", first_line) or re.match(r"^\[\d+\]", first_line)):
        if density > 0.8:
            return True

    return False


def _metadata_looks_garbled(title, authors, year, journal):
    """Detect garbled metadata (mis-parsed PDFs, etc.)."""
    t = str(title or "").strip()
    a = str(authors or "").strip()
    y = str(year or "").strip()
    j = str(journal or "").strip()

    if len(t) > 15 and " " not in t:
        return True
    a_lower = a.lower()
    if any(m in a_lower for m in ("editor", "series", "ethods in", "olecular biology")):
        return True
    if y and not re.fullmatch(r"(19|20)\d{2}", y):
        return True
    if j and re.fullmatch(r"\d+[\-–]\d+", j):
        return True
    return False


def _get_doc_info(chunk):
    """Extract a human-readable paper header from chunk metadata."""
    if not isinstance(chunk, dict):
        return None

    meta = chunk.get("metadata", {})
    if not isinstance(meta, dict):
        return None

    doc_meta = meta.get("doc_metadata", {})
    if isinstance(doc_meta, dict):
        title = str(doc_meta.get("title", "")).strip()
        authors = str(doc_meta.get("authors", "")).strip()
        journal = str(doc_meta.get("journal", "")).strip()
        year = str(doc_meta.get("year", "")).strip()

        if title and not _metadata_looks_garbled(title, authors, year, journal):
            header = f'"{title}"'
            if authors:
                header += f" by {authors}"
            if journal or year:
                header += " ("
                if journal:
                    header += journal
                if year:
                    if journal:
                        header += ", "
                    header += year
                header += ")"
            return header

    # Fallback: parse from document name/title field
    title = str(chunk.get("title", "")).strip()
    if title:
        title = re.sub(r"__[a-z_]+_\d{10,}(?:\.pdf)?$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE).strip()
        if title:
            parts = [p.strip() for p in title.split(",")]
            if len(parts) >= 3:
                maybe_authors = parts[0]
                maybe_year = parts[1].strip()
                maybe_journal = parts[2].strip()
                if re.fullmatch(r"(19|20)\d{2}", maybe_year):
                    header = f'"{title}"'
                    if maybe_authors:
                        header += f" by {maybe_authors}"
                    header += f" ({maybe_journal}, {maybe_year})"
                    return header
            return title

    return None


def _process_chunks(chunks, filter_refs=True):
    """Process retrieval chunks: extract text, optionally filter references,
    prepend paper metadata headers.

    Args:
        chunks: Raw retrieval result list.
        filter_refs: If True, filter out reference/bibliography chunks.

    Returns:
        (kept_chunks, removed_count, seen_docs)
    """
    kept = []
    removed = 0
    seen_docs = set()

    for c in chunks:
        text = _extract_text(c)
        if not text or len(text) < 20:
            continue

        if filter_refs and _is_reference_chunk(text):
            removed += 1
            continue

        doc_name = _get_doc_info(c)
        if doc_name:
            seen_docs.add(doc_name)
            text = "From paper: " + doc_name + NL + text

        kept.append(text)

    return kept, removed, seen_docs


# Accepts both 'kr_result' (Dify configured name) and 'result' (fallback)
def main(result=None, kr_result=None, **kwargs):
    raw_chunks = kr_result if kr_result is not None else result
    if not isinstance(raw_chunks, list):
        return {
            "filtered_chunks": [],
            "chunk_count": 0,
            "chunks_removed": 0,
            "doc_names": []
        }

    kept, removed, seen_docs = _process_chunks(raw_chunks, filter_refs=True)

    # Safety fallback: if filtering removed too many chunks, retry without filter
    if len(kept) < 3 and len(raw_chunks) >= 3:
        kept, removed, seen_docs = _process_chunks(raw_chunks, filter_refs=False)
        removed = 0

    # Deduplicate: keep max 1 chunk per paper
    by_doc = {}
    for chunk in kept:
        parts = chunk.split(NL, 1)
        doc_key = parts[0] if parts[0].startswith("From paper:") else "_unknown"
        content = parts[1] if len(parts) > 1 else chunk
        if doc_key not in by_doc:
            by_doc[doc_key] = []
        by_doc[doc_key].append(content)

    deduped = []
    for doc_key, contents in by_doc.items():
        merged = NL.join(contents[:1])  # Keep max 1 chunk per paper
        deduped.append(doc_key + NL + merged)

    if not deduped:
        deduped.append(
            "ALL " + str(len(raw_chunks)) + " RETRIEVED CHUNKS WERE REFERENCE LISTS "
            "AND FILTERED OUT. The query may match bibliography sections rather "
            "than paper body text. Try a more specific query or different search terms."
        )

    return {
        "filtered_chunks": deduped[:30],
        "chunk_count": min(len(deduped), 30),
        "chunks_removed": removed,
        "doc_names": sorted(seen_docs)[:30]
    }