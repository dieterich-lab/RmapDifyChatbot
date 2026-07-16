# Code Node: Update Paper Memory
# Node ID: 1778800001002


def _normalize_obj(item):
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    authors = str(item.get("authors") or item.get("author") or "").strip()
    year = str(item.get("year") or "").strip()
    journal = str(item.get("journal") or "").strip()
    doc_id = str(item.get("doc_id") or "").strip()
    if not any([title, authors, year, journal]):
        return None
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doc_id": doc_id,
    }


def _parse_from_iteration_output(iteration_output):
    parsed = []
    if not isinstance(iteration_output, list):
        return parsed

    for block in iteration_output:
        if not isinstance(block, str):
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" not in line:
                continue
            # Strip leading numbering like "1. "
            if ". " in line:
                _, _, line = line.partition(". ")
            parts = [p.strip() for p in line.split("|")]
            # Accept 3-5 parts: title | [authors] | year | journal | [doc_id]
            if len(parts) < 3 or len(parts) > 5:
                continue
            obj_dict = {}
            if len(parts) == 3:
                obj_dict = {"title": parts[0], "year": parts[1], "journal": parts[2]}
            elif len(parts) == 4:
                obj_dict = {
                    "title": parts[0],
                    "authors": parts[1],
                    "year": parts[2],
                    "journal": parts[3],
                }
            else:  # 5 parts
                obj_dict = {
                    "title": parts[0],
                    "authors": parts[1],
                    "year": parts[2],
                    "journal": parts[3],
                    "doc_id": parts[4],
                }
            obj = _normalize_obj(obj_dict)
            if obj is not None:
                parsed.append(obj)
    return parsed


def _dedupe(items):
    unique = {}
    for item in items:
        obj = _normalize_obj(item)
        if obj is None:
            continue
        key = (
            obj["title"].lower(),
            obj["authors"].lower(),
            obj["year"],
            obj["journal"].lower(),
        )
        if key not in unique:
            unique[key] = obj
    return list(unique.values())


def main(iteration_output=None, memory=None):
    parsed_docs = _dedupe(_parse_from_iteration_output(iteration_output))
    if parsed_docs:
        return {"memory": parsed_docs}

    # If parsing failed, return existing memory (don't overwrite with empty)
    existing = memory if isinstance(memory, list) else []
    if existing:
        return {"memory": _dedupe(existing)}

    # Last resort: return empty
    return {"memory": []}
