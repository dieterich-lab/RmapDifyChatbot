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


def main(knowledge_text=None, metadata_text=None):
    parts = []
    first = _strip_think(knowledge_text)
    second = _strip_think(metadata_text)
    if first:
        parts.append(first)
    if second:
        parts.append(second)
    merged = "\n\n".join(parts).strip()
    return {"cleaned_text": merged}
