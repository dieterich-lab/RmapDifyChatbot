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
    # Fallback: use result_text from Metadata Query only if metadata_text is empty
    if not parts:
        rt = kwargs.get("result_text")
        if rt:
            cleaned = _strip_think(rt)
            if cleaned:
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
