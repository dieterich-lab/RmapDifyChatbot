# Code Node: Parse Extractor Paper List
# Node ID: 1778800001010

import json
import re


def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())[:300]
    if isinstance(value, dict):
        for key in ("value", "name", "author", "authors", "text"):
            if key in value:
                return _to_text(value.get(key))
        return ", ".join(str(v).strip() for v in value.values() if str(v).strip())[:300]
    return str(value).strip()[:300]


def _clean_obj(item):
    if not isinstance(item, dict):
        return None
    year_value = _to_text(item.get("year"))
    return {
        "title": _to_text(item.get("title")),
        "authors": _to_text(item.get("authors") or item.get("author")),
        "year": year_value if re.fullmatch(r"^(19|20)[0-9]{2}$", year_value) else "",
        "journal": _to_text(item.get("journal")),
    }


def _parse_json(extractor_text):
    if isinstance(extractor_text, (dict, list)):
        return extractor_text
    if not isinstance(extractor_text, str):
        return {}
    text = extractor_text.strip()
    if not text:
        return {}
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, (dict, list)) else {}


def _clean_list(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        obj = _clean_obj(item)
        if obj is not None and any(obj.values()):
            cleaned.append(obj)
    return cleaned


def main(extractor_text=None, extractor_structured_output=None):
    data = extractor_structured_output if isinstance(extractor_structured_output, (dict, list)) else _parse_json(extractor_text)

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data.get("paper_list"), list):
        raw_items = data.get("paper_list")
    elif any(k in data for k in ("title", "authors", "author", "year", "journal")):
        raw_items = [data]
    elif isinstance(data.get("authors"), list):
        raw_items = [{"authors": a} for a in data.get("authors") if str(a).strip()]
    else:
        raw_items = []

    return {"extracted_paper_list": _clean_list(raw_items)}
