# Code Node: Parse Router Output
# Node ID: 1778800001033

import json
import re

# ── Shared helpers ──────────────────────────────────────────────────

def _clean_paper(item):
    """Normalize a paper dict from LLM output or conversation memory."""
    if not isinstance(item, dict):
        return None
    obj = {
        "title": str(item.get("title") or "").strip(),
        "authors": str(item.get("authors") or item.get("author") or "").strip(),
        "year": str(item.get("year") or "").strip(),
        "journal": str(item.get("journal") or "").strip(),
    }
    doc_id = str(item.get("doc_id") or "").strip()
    if doc_id:
        obj["doc_id"] = doc_id
    return obj if any(obj.values()) else None


def _clean_paper_list(items):
    """Clean and filter a list of paper dicts."""
    result = []
    for item in (items if isinstance(items, list) else []):
        if isinstance(item, dict):
            c = _clean_paper(item)
            if c:
                result.append(c)
    return result


def _papers_from_memory(mem):
    """Extract cleaned paper list from conversation memory."""
    return _clean_paper_list(mem)


def _render_paper_list_text(paper_list):
    """Human-readable rendering of paper_list for plain (non-Jinja) prompt
    fields, which can't directly interpolate Array[object] variables."""
    if not paper_list:
        return ""
    lines = []
    for idx, p in enumerate(paper_list, start=1):
        if not isinstance(p, dict):
            continue
        parts = [p.get("title") or "(untitled)"]
        if p.get("authors"):
            parts.append(p["authors"])
        if p.get("year"):
            parts.append(p["year"])
        if p.get("journal"):
            parts.append(p["journal"])
        lines.append(f"{idx}. " + " | ".join(parts))
    return "\n".join(lines)


def _fallback_result():
    """Fallback when router JSON is unparseable."""
    return {
        "intent": "knowledge_retrieval",
        "paper_list": [],
        "paper_list_text": "",
        "paper_count": 0,
        "rewritten_query": "",
        "list_mode": "papers",
        "collaboration_mode": "",
        "year": "",
    }


# ── Guard functions ─────────────────────────────────────────────────
# Each guard inspects the user query and optionally overrides
# intent/paper_list. Returns a dict of overrides, or None if no match.

def _guard_table_query(query):
    """Route table-related questions -> entity_lookup.
    Examples: 'What is in Table 2?', 'Show me Table 3'
    """
    q = query.lower()

    # Exclude "table of contents"
    if re.search(r"\btable\s+of\s+contents\b|\bcontents\s+table\b", q):
        return None

    explicit = bool(re.search(
        r"\b(?:table|tab\.?)\s*(?:s\d+|\d+[a-z]?|[ivxlcdm]+)\b", q, re.I
    ))
    terms = bool(re.search(r"\b(?:tables?|tabular|rows?|columns?)\b", q, re.I))
    question = bool(re.search(
        r"\b(?:"
        r"what(?:'s| is| are)?\s+(?:in|shown|reported|listed|presented)\s+(?:in\s+)?(?:the\s+)?tables?"
        r"|what\s+does\s+(?:the\s+)?table\s+(?:show|report|contain|say)"
        r"|which\s+.+\s+(?:are|is)\s+(?:listed|shown|reported|presented)\s+in\s+(?:the\s+)?table"
        r"|(?:find|show(?:\s+me)?|list)\s+(?:the\s+)?tables?"
        r")\b", q, re.I
    ))

    if explicit or terms or question:
        return {"intent": "entity_lookup"}
    return None


def _guard_name_only(query, intent):
    """Route bare person names -> paper_list.
    Patterns: 'Helm, Mark', 'M. Helm', 'Dieterich' (1-2 words, no question words).
    Only fires if router classified as author_lookup or knowledge_retrieval.
    """
    if intent not in ("author_lookup", "knowledge_retrieval"):
        return None

    q = query.strip()
    _QUESTION_WORDS = {
        "who", "what", "which", "how", "why", "where", "when",
        "summarize", "compare", "group", "find", "list", "show",
        "experience", "worked", "using", "studied",
    }

    has_comma = "," in q and len(q.split(",")) == 2
    has_dot_initials = bool(re.match(r"^[A-ZÀ-ÖØ-Ý]\.\s+\w{2,}$", q))
    one_or_two_words = (
        len(q.split()) in (1, 2)
        and not re.search(r"[.?!/]", q)
        and not any(w.lower() in q.lower() for w in _QUESTION_WORDS)
    )

    if has_comma or has_dot_initials or one_or_two_words:
        return {
            "intent": "paper_list",
            "paper_list": [{"authors": q, "title": "", "year": "", "journal": ""}],
            "bypass": True,
        }
    return None


def _guard_find_papers_by(query):
    """Route 'find/show papers/publications/articles by <name>' -> paper_list."""
    q = query.strip().lower()
    prefixes = (
        "find papers by ", "show papers by ",
        "find publications by ", "show publications by ",
        "find articles by ", "show articles by ",
    )
    if not any(q.startswith(p) for p in prefixes):
        return None

    parts = q.split(" by ", 1)
    if len(parts) == 2:
        name = parts[1].strip().rstrip(".,;")
        if name and len(name) >= 2:
            return {
                "intent": "paper_list",
                "paper_list": [{"authors": name, "title": "", "year": "", "journal": ""}],
                "bypass": True,
            }
    return None


def _guard_identify_multi(query):
    """Route 'Identify: X, Y, Z' or 'which papers are by X, Y' -> paper_list."""
    q = query.strip().lower()
    prefixes = ("identify:", "identify ", "can you identify ", "which papers are by ")
    if not any(q.startswith(p) for p in prefixes):
        return None

    name_part = q
    for prefix in prefixes:
        if name_part.startswith(prefix):
            name_part = name_part[len(prefix):]
            break
    name_part = name_part.strip().rstrip(".,;?!")

    if name_part and "," in name_part:
        names = [n.strip() for n in name_part.split(",") if n.strip()]
        if len(names) >= 2:
            return {
                "intent": "paper_list",
                "paper_list": [
                    {"authors": n, "title": "", "year": "", "journal": ""}
                    for n in names
                ],
                "bypass": True,
            }
    return None


def _extract_collab_target(q_lower, q_orig):
    """Extract the target author name from a collaboration query.
    Returns (single_target, dual_target) - at most one will be non-empty.
    """
    _SINGLE_PATTERNS = [
        (r"(?:co-?authors?|collaborators?|collaborations?)\s+of\s+", "after"),
        (r"(?:co-?authors?|collaborated|collaborations?|published)\s+with\s+", "after"),
        (r"(?:co-authors?\s+(?:has\s+)?|coauthors?\s+(?:has\s+)?)([\w\s.-]+?)\s+(?:published|collaborated)\s+with", "group1"),
        (r"(?:collaborat\w*|co-?author\w*|publish\w*|work\w*)\b(?:(?!\bwith\b).){0,40}?\bwith\s+([\w.\-]+(?:\s+[\w.\-]+){0,3})", "group1"),
        (r"([\w.\-]+(?:\s+[\w.\-]+){0,3})'s\s+(?:collaborat\w*|co-?author\w*)", "group1"),
        (r"(?:who\s+(?:does|did|has)\s+|does\s+|did\s+)([\w.\-]+(?:\s+[\w.\-]+){0,3}?)\s+(?:collaborate\w*|collaborated|co-?author\w*|publish\w*|work\w*)\b", "group1"),
        (r"(?:collaborators?|co-?authors?)\s+does\s+([\w.\-]+(?:\s+[\w.\-]+){0,3})\s+have\b", "group1"),
    ]

    _GENERIC_WORDS = {
        "anyone", "someone", "anybody", "somebody", "others",
        "each other", "them", "him", "her", "anyone else",
    }

    target = ""
    for pattern, mode in _SINGLE_PATTERNS:
        if target:
            break
        m = re.search(pattern, q_lower)
        if not m:
            continue
        if mode == "after":
            candidate = q_orig[m.end():].strip().rstrip(".,;?!")
        else:  # group1
            candidate = q_orig[m.start(1):m.end(1)].strip().rstrip(".,;?!")
            candidate = re.split(
                r"\s+(?:the most|most often|the paper|papers?)\b", candidate
            )[0].strip()
        if candidate and len(candidate) > 1 and candidate.lower() not in _GENERIC_WORDS:
            target = candidate

    # Dual-author detection: "co-authored by X and Y", "X and Y collaboration"
    dual_target = ""
    _DUAL_PATTERNS = [
        r"collaborat\w*\s+between\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)",
        r"co[- ]?authored?\s+by\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)",
        r"how\s+many\s+papers\s+(?:do|have)\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:share|co[- ]?author|publish)",
        r"([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+collaborat",
        r"do\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:share|have|co[- ]?author)",
        r"([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:published|co[- ]?authored|share|shared|joint)",
    ]
    for pattern in _DUAL_PATTERNS:
        m = re.search(pattern, q_lower)
        if m:
            n1 = q_orig[m.start(1):m.end(1)].strip().rstrip(".,;?!")
            n2 = q_orig[m.start(2):m.end(2)].strip().rstrip(".,;?!")
            if n1 and n2 and len(n1) > 1 and len(n2) > 1:
                dual_target = f"{n1}|{n2}"
            break

    return target, dual_target


def _guard_collaboration(query):
    """Route collaboration queries -> paper_list with collaboration_mode.
    Detects 'who collaborated most', 'co-authors of X', 'published together'.
    """
    q = query.strip().lower()
    q_orig = query.strip()

    _COLLAB_MARKERS = (
        "collaborat", "co-author", "coauthor", "co author",
        "co-authored", "coauthored", "published together",
        "publish together", "published with", "worked together",
        "work together", "co-autoren",
    )
    has_share = bool(re.search(
        r"\bshare[ds]?\b.*\bpaper\b|\bpaper.*\bshare[ds]?\b|\bshare[ds]?\s*\?", q
    ))

    if not (any(m in q for m in _COLLAB_MARKERS) or has_share):
        return None

    year = ""
    year_match = re.search(r"\b(19|20)\d{2}\b", q)
    if year_match:
        year = year_match.group(0)

    target, dual_target = _extract_collab_target(q, q_orig)
    collaboration_mode = (
        dual_target if dual_target
        else (target if target else "all")
    )

    return {
        "intent": "paper_list",
        "paper_list": [],
        "bypass": True,
        "collaboration_mode": collaboration_mode,
        "year": year,
    }


def _guard_what_else(query, mem):
    """Route 'what else did X publish?' follow-ups -> metadata_list.
    Extracts author from conversation memory (previous turn).
    """
    q = query.strip().lower()
    is_what_else = (
        q.startswith("what else ")
        or q.startswith("anything else ")
        or "what else has " in q
        or "what else did " in q
    )
    if not is_what_else or not mem:
        return None

    prev_authors = set()
    for item in mem:
        if isinstance(item, dict):
            a = str(item.get("authors", "")).strip()
            if a:
                prev_authors.add(a)

    if prev_authors:
        return {
            "intent": "metadata_list",
            "paper_list": [{"authors": list(prev_authors)[0], "title": "", "year": "", "journal": ""}],
            "bypass": True,
        }
    return None


def _guard_year_authors(query):
    """Route 'which authors published in <year>?' -> metadata_list.
    Router tends to misclassify this as entity_lookup.
    """
    q = query.strip().lower()
    m = re.search(
        r"(?:which|what)\s+(?:authors?|researchers?)\s+(?:have\s+)?published\s+in\s+((?:19|20)\d{2})"
        r"|who\s+(?:has\s+)?published\s+in\s+((?:19|20)\d{2})"
        r"|(?:authors?|researchers?)\s+(?:who|that)\s+published\s+in\s+((?:19|20)\d{2})",
        q,
    )
    if not m:
        return None

    year_val = next(g for g in m.groups() if g)
    return {
        "intent": "metadata_list",
        "list_mode": "authors",
        "paper_list": [{"authors": "", "title": "", "year": year_val, "journal": ""}],
        "year": year_val,
    }


def _guard_metadata_followup(query, mem):
    """Route metadata-only follow-ups -> metadata_list.
    E.g. 'When did this paper get published?', 'What journal is this in?'
    These should NOT trigger content_summary's full-text fetch.
    """
    if not mem:
        return None

    q = query.strip().lower()
    _METADATA_MARKERS = (
        "when did this paper", "when was this paper", "when did the paper",
        "when was it published", "when was this published", "what year was this",
        "what journal is this", "which journal is this", "what journal was this published in",
        "who wrote this", "who are the authors of this", "who authored this",
        "wann wurde das veröffentlicht", "wann wurde dies veröffentlicht",
        "wann wurde der artikel veröffentlicht",
    )
    if not any(marker in q for marker in _METADATA_MARKERS):
        return None

    _CONTENT_MARKERS = (
        "summarize", "summarise", "compare", "methods", "method",
        "findings", "results", "analyze", "analyse", "discuss", "explain",
        "key points", "abstract", "conclusion", "what did they",
        "how did they", "zusammenfass",
    )
    if any(m in q for m in _CONTENT_MARKERS):
        return None

    from_memory = _papers_from_memory(mem)
    if from_memory:
        return {"intent": "metadata_list", "paper_list": from_memory}
    return None


# ── Main function ───────────────────────────────────────────────────

def main(router_text=None, conversation_memory=None, sys_query=None):
    text = str(router_text or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return _fallback_result()
    try:
        obj = json.loads(m.group())
    except Exception:
        return _fallback_result()

    intent = str(obj.get("intent", "")).strip()
    if intent not in (
        "metadata_list", "paper_list", "content_summary",
        "knowledge_retrieval", "author_lookup", "entity_lookup",
    ):
        intent = "knowledge_retrieval"

    list_mode = str(obj.get("list_mode") or "").strip()
    if list_mode not in ("papers", "authors"):
        list_mode = "papers"

    mem = conversation_memory if isinstance(conversation_memory, list) else []
    collaboration_mode = ""
    year = ""

    paper_list = obj.get("paper_list")
    if paper_list == "use_memory":
        paper_list = _papers_from_memory(mem)
    elif isinstance(paper_list, list):
        paper_list = _clean_paper_list(paper_list)
    else:
        paper_list = []

    # Auto-fallback for content_summary: use memory if paper_list is empty
    # (handles "Summarize them" follow-ups). NOT for metadata_list where
    # empty paper_list means "all papers".
    if not paper_list and intent == "content_summary" and mem:
        paper_list = _papers_from_memory(mem)

    # Cap papers for content_summary to fit in the 131K context window
    MAX_PAPERS_FOR_SUMMARY = 37
    if intent == "content_summary":
        paper_list = paper_list[:MAX_PAPERS_FOR_SUMMARY]

    rw = str(obj.get("rewritten_query") or "").strip()
    if not rw and sys_query:
        rw = str(sys_query).strip()

    query = str(sys_query or "").strip()

    multi_author_bypass = False

    if query:
        result = _guard_table_query(query)
        if result:
            intent = result["intent"]

        result = _guard_name_only(query, intent)
        if result:
            intent = result["intent"]
            if not paper_list:
                paper_list = result["paper_list"]
            if result.get("bypass"):
                multi_author_bypass = True

        result = _guard_find_papers_by(query)
        if result:
            intent = result["intent"]
            paper_list = result["paper_list"]
            if result.get("bypass"):
                multi_author_bypass = True

        result = _guard_identify_multi(query)
        if result:
            intent = result["intent"]
            paper_list = result["paper_list"]
            if result.get("bypass"):
                multi_author_bypass = True

        result = _guard_collaboration(query)
        if result:
            intent = result["intent"]
            paper_list = result["paper_list"]
            collaboration_mode = result.get("collaboration_mode", "")
            year = result.get("year", year)
            if result.get("bypass"):
                multi_author_bypass = True

        result = _guard_what_else(query, mem)
        if result:
            intent = result["intent"]
            paper_list = result["paper_list"]
            if result.get("bypass"):
                multi_author_bypass = True

        result = _guard_year_authors(query)
        if result:
            intent = result["intent"]
            list_mode = result.get("list_mode", list_mode)
            paper_list = result["paper_list"]
            year = result.get("year", year)

        result = _guard_metadata_followup(query, mem)
        if result:
            intent = result["intent"]
            paper_list = result["paper_list"]

    # ── Multi-author bypass: skip Metadata LLM ───────────────────────
    # For metadata_list queries with multiple distinct authors (comma-separated
    # or split across paper_list entries), metadata_query produces pre-formatted
    # output. The Metadata LLM (qwen2.5:14b) cannot reliably pass through
    # OR-matched results. Setting paper_count=0 routes through the Metadata LLM
    # Bypass directly to Final Answer Sanitizer, which passes result_text through.
    if intent == "metadata_list" and paper_list:
        all_authors = []
        for entry in paper_list:
            if isinstance(entry, dict):
                a = str(entry.get("authors", "")).strip()
                if a:
                    all_authors.append(a)
        has_comma = any("," in a for a in all_authors)
        if has_comma or len(all_authors) >= 2:
            multi_author_bypass = True

    return {
        "intent": intent,
        "paper_list": paper_list,
        "paper_list_text": _render_paper_list_text(paper_list),
        "paper_count": (
            1 if intent == "metadata_list"
            else 0 if intent == "paper_list"
            else len(paper_list)
        ),
        "rewritten_query": rw,
        "list_mode": list_mode,
        "collaboration_mode": collaboration_mode,
        "year": year,
    }