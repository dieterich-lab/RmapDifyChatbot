# Code Node: Follow-up Memory Subset
# Node ID: 1778800001012

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
        "doc_id": str(item.get("doc_id") or "").strip(),
    }


def _clean_list(items):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        obj = _clean_obj(item)
        if obj is not None and any(obj.values()):
            cleaned.append(obj)
    return cleaned


def _extract_limit(query):
    text = str(query or "").strip().lower()
    if not text:
        return None
    for pattern in (r"\btop\s+(\d{1,2})\b", r"\bfirst\s+(\d{1,2})\b", r"\bersten?\s+(\d{1,2})\b"):
        m = re.search(pattern, text)
        if m:
            n = int(m.group(1))
            return n if n > 0 else None
    if re.search(r"\bfirst\s+two\b|\bersten?\s+zwei\b", text):
        return 2
    if re.search(r"\bfirst\s+three\b|\bersten?\s+drei\b", text):
        return 3
    if re.search(r"\bfirst\s+one\b|\bersten?\s+eins\b", text):
        return 1
    return None


def _extract_year(item):
    text = _to_text((item or {}).get("year"))
    return int(text) if re.fullmatch(r"^(19|20)[0-9]{2}$", text) else -1


def main(memory=None, query=None, is_followup=True):
    if not is_followup:
        return {"memory_subset": []}

    items = _clean_list(memory)
    if not items:
        return {"memory_subset": []}

    text = str(query or "").strip().lower()
    if re.search(r"\b(newest|latest|most recent|neueste[snrm]?)\b", text):
        sorted_items = sorted(items, key=_extract_year, reverse=True)
        if _extract_year(sorted_items[0]) != -1:
            return {"memory_subset": sorted_items[:1]}

    if re.search(r"\b(oldest|earliest|aelteste[snrm]?|älteste[snrm]?)\b", text):
        sorted_items = sorted(items, key=_extract_year, reverse=False)
        if _extract_year(sorted_items[0]) != -1:
            return {"memory_subset": sorted_items[:1]}

    limit = _extract_limit(text)
    if isinstance(limit, int):
        return {"memory_subset": items[:limit]}

    return {"memory_subset": items}
