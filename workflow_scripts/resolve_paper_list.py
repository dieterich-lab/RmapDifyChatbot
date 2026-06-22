# Code Node: Resolve Paper List
# Node ID: 1778800001001

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


def main(extracted_paper_list=None, memory_subset=None, is_followup=True, query=None):
    extracted = _clean_list(extracted_paper_list)
    subset = _clean_list(memory_subset)

    if subset:
        return {"paper_list": subset, "paper_count": len(subset)}

    if extracted:
        return {"paper_list": extracted, "paper_count": len(extracted)}

    q = str(query or "").strip()
    m = re.search(r"\b(?:by|von)\s+([A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){1,4})", q)
    if m:
        return {
            "paper_list": [
                {
                    "title": "",
                    "authors": m.group(1).strip(" ,.;:"),
                    "year": "",
                    "journal": "",
                }
            ],
            "paper_count": 1
        }

    return {"paper_list": [], "paper_count": 0}
