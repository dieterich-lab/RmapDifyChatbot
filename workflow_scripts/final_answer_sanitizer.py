# Code Node: Final Answer Sanitizer
# Node ID: 1778800001013

import re


def _strip_think(text):
    cleaned = str(text or "")
    # Remove well-formed think blocks first.
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I)
    # Also handle truncated outputs where </think> is missing.
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
    merged = "\n\n".join(parts).strip()
    return {"cleaned_text": merged}
