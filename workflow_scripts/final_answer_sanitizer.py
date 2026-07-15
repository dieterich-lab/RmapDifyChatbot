# Code Node: Final Answer Sanitizer
# Node ID: 1778800001013

import json
import re


def _strip_think(text):
    cleaned = str(text or "")
    # Remove well-formed think blocks first.
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I)
    # Also handle truncated outputs where </think> is missing.
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.S | re.I)
    return cleaned.strip()


def _build_author_lookup(filtered_chunks):
    """Build a dict mapping paper titles to full author lists from chunk metadata."""
    lookup = {}
    if not isinstance(filtered_chunks, list):
        return lookup

    for chunk in filtered_chunks:
        if not isinstance(chunk, dict):
            continue
        meta = chunk.get("metadata", {})
        if not isinstance(meta, dict):
            continue
        doc_meta = meta.get("doc_metadata", {})
        if not isinstance(doc_meta, dict):
            continue

        title = str(doc_meta.get("title", "")).strip()
        authors = str(doc_meta.get("authors", "")).strip()

        if title and authors:
            # Normalize title for fuzzy matching
            key = _normalize_title(title)
            if key not in lookup:
                lookup[key] = authors

    return lookup


def _normalize_title(title):
    """Normalize a title for comparison."""
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _enrich_extraction_text(extraction_text, author_lookup):
    """Replace single-author lines with full author lists."""
    if not extraction_text or not author_lookup:
        return extraction_text

    lines = extraction_text.split("\n")
    result = []
    current_title = None

    for line in lines:
        # Detect paper title lines: **"Title"** (Journal, Year)
        title_match = re.match(r'\*\*"([^"]+)"\*\*', line)
        if title_match:
            current_title = title_match.group(1)
            result.append(line)
            continue

        # Detect author lines: - AuthorName: "quote"
        author_match = re.match(r"^(\s*-\s+)([^:]+)(:\s*\"[^\"]+\".*)$", line)
        if author_match and current_title:
            prefix = author_match.group(1)
            quote_part = author_match.group(3)

            # Look up full author list
            key = _normalize_title(current_title)
            full_authors = author_lookup.get(key, "")

            if full_authors and "," in full_authors:
                # Replace single author with full list
                result.append(f"{prefix}{full_authors}{quote_part}")
            else:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def main(**kwargs):
    parts = []
    for key in (
        "extraction_text",
        "entity_text",
        "summary_text",
        "knowledge_text",
        "metadata_text",
    ):
        text = kwargs.get(key)
        if text:
            cleaned = _strip_think(text)
            if cleaned:
                # Enrich extraction_text with full author lists
                if key == "extraction_text":
                    filtered_chunks = kwargs.get("filtered_chunks", [])
                    author_lookup = _build_author_lookup(filtered_chunks)
                    cleaned = _enrich_extraction_text(cleaned, author_lookup)

                parts.append(cleaned)
    merged = "\n\n".join(parts).strip()
    if not merged:
        merged = (
            "I could not generate a meaningful answer for your query. "
            "This may be because the search was too broad or did not match any documents.\n\n"
            "Suggestions:\n"
            "- For paper listings: try 'Papers by <author name>' or 'Papers from <year>'\n"
            "- For topic searches: try 'What is m6A?' or 'Which methods detect RNA modifications?'\n"
            "- For author lookups: try 'Who has worked on tRNA modifications?'\n"
            "- For entity lookups: try 'Which RNA modifications are most studied?'"
        )
    return {"cleaned_text": merged}
