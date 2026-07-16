# Code Node: Final Answer Sanitizer
# Node ID: 1778800001013

import re


def _strip_think(text):
    cleaned = str(text or "")
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.S | re.I)
    return cleaned.strip()


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
                parts.append(cleaned)

    # Fallback: use result_text from Metadata Query only if no meaningful LLM output
    rt = kwargs.get("result_text")
    if rt:
        cleaned = _strip_think(rt)
        is_meaningful = (
            cleaned
            and len(cleaned) > 50
            and "Insufficient context" not in cleaned
            and "Keine Dokumente gefunden" not in cleaned
        )
        # Check if all LLM outputs are weak (empty, short, or negative)
        _WEAK_MARKERS = [
            "Insufficient",
            "Keine Dokumente",
            "cannot determine",
            "cannot answer",
            "no relevant",
            "does not contain",
            "does not provide",
            "not found",
            "not available",
            "unable to",
            "I could not",
            "I cannot",
        ]

        def _is_weak(text):
            t = text.strip()
            if len(t) < 40:
                return True
            t_lower = t.lower()
            return any(m.lower() in t_lower for m in _WEAK_MARKERS)

        # If no LLM parts OR all LLM parts are weak, use result_text
        if is_meaningful and (not parts or all(_is_weak(p) for p in parts)):
            parts = [cleaned]  # Replace, don't append
        elif not parts and cleaned:
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
