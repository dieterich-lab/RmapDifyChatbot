import re


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


# Matches the header line emitted by the Fetch Full Paper node:
#   === <title> (<year>, <journal>) — <authors> ===
# Title match is greedy on purpose: titles like "Detecting m(6)A at
# single-molecular resolution..." contain their own parentheses, so a
# non-greedy match would stop at the first ")" instead of the last
# "(YYYY, journal) — authors ===" segment before the closing "===".
_HEADER_RE = re.compile(
    r"^===\s*(?P<title>.+?)\s*\((?P<year>\d{4}),\s*(?P<journal>[^)]*)\)\s*—\s*(?P<authors>.*?)\s*===\s*$"
)


def _parse_from_iteration_output(iteration_output):
    parsed = []
    if not isinstance(iteration_output, list):
        return parsed

    for block in iteration_output:
        if not isinstance(block, str):
            continue
        # The paper's metadata header is always the first non-empty line
        # of each block (see Fetch Full Paper's `header = f"=== {meta_line} ==="`).
        first_line = ""
        for line in block.splitlines():
            line = line.strip()
            if line:
                first_line = line
                break
        if not first_line.startswith("==="):
            continue
        m = _HEADER_RE.match(first_line)
        if not m:
            continue
        obj = _normalize_obj(
            {
                "title": m.group("title"),
                "year": m.group("year"),
                "journal": m.group("journal"),
                "authors": m.group("authors"),
            }
        )
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