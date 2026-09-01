# Code Node: Parse Router Output
# Node ID: 1778800001033

import json
import re


def _clean_paper(item):
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


def _fallback_result():
    """Fallback when router JSON is unparseable."""
    return {
        "intent": "knowledge_retrieval",
        "paper_list": [],
        "paper_count": 0,
        "rewritten_query": "",
        "list_mode": "papers",
    }


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


def main(router_text=None, conversation_memory=None, sys_query=None):
    text = str(router_text or "").strip()
    # Strip <think> tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    # Find JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return _fallback_result()
    try:
        obj = json.loads(m.group())
    except Exception:
        return _fallback_result()

    intent = str(obj.get("intent", "")).strip()
    if intent not in (
        "metadata_list",
        "paper_list",
        "content_summary",
        "knowledge_retrieval",
        "author_lookup",
        "entity_lookup",
    ):
        intent = "knowledge_retrieval"

        # ── Table-query routing guard ───────────────────────────────
    # Table-related questions are content/entity extraction queries.
    # Route them directly to entity_lookup so they do not fall through
    # to generic knowledge_retrieval, paper_list, or the name-only guard.
    #
    # Examples:
    #   "What is in Table 2?"
    #   "Show me Table 3"
    #   "Which genes are listed in Table 1?"
    #   "What does the table say about TP53?"
    #   "Which authors are in the table?"
    #   "Find tables containing survival data"

    table_query = False

    if sys_query:
        q_table = str(sys_query).strip().lower()

        # Explicit table references:
        # table 1, table 2, table 3a, table S1, supplemental table 2, etc.
        explicit_table_ref = bool(
            re.search(
                r"\b(?:table|tab\.?)\s*"
                r"(?:s\d+|\d+[a-z]?|[ivxlcdm]+)\b",
                q_table,
                re.IGNORECASE,
            )
        )

        # General table terminology.
        table_terms = bool(
            re.search(
                r"\b(?:tables?|tabular|rows?|columns?)\b",
                q_table,
                re.IGNORECASE,
            )
        )

        # Common table-oriented question patterns.
        table_question = bool(
            re.search(
                r"\b(?:"
                r"what(?:'s| is| are)?\s+(?:in|shown|reported|listed|presented)\s+(?:in\s+)?"
                r"(?:the\s+)?tables?"
                r"|"
                r"what\s+does\s+(?:the\s+)?table\s+(?:show|report|contain|say)"
                r"|"
                r"which\s+.+\s+(?:are|is)\s+(?:listed|shown|reported|presented)\s+in\s+(?:the\s+)?table"
                r"|"
                r"find\s+(?:the\s+)?tables?"
                r"|"
                r"show\s+(?:me\s+)?(?:the\s+)?tables?"
                r"|"
                r"list\s+(?:the\s+)?(?:rows?|columns?|entries|values)\s+(?:in|from)\s+(?:the\s+)?table"
                r")\b",
                q_table,
                re.IGNORECASE,
            )
        )

        # Avoid interpreting "table of contents" as a paper table.
        table_of_contents = bool(
            re.search(
                r"\btable\s+of\s+contents\b|\bcontents\s+table\b",
                q_table,
                re.IGNORECASE,
            )
        )

        table_query = (
            not table_of_contents
            and (explicit_table_ref or table_question or table_terms)
        )

    if table_query:
        intent = "entity_lookup"

    # ── Read list_mode from router JSON (LLM-native, no regex) ──
    list_mode = str(obj.get("list_mode") or "").strip()
    if list_mode not in ("papers", "authors"):
        list_mode = "papers"  # default

    paper_list = obj.get("paper_list")
    mem = conversation_memory if isinstance(conversation_memory, list) else []
    # Tracks whether paper_list was populated by a deterministic, code-level
    # filter (as opposed to the router's own free-form extraction). Any such
    # case should skip the Metadata LLM entirely - it cannot reliably
    # pass through exact filter results (see "Multi-author bypass" below),
    # a failure mode that applies just as much to single-author filters.
    multi_author_bypass = False

    # If paper_list is the string "use_memory", populate from conversation.memory
    if paper_list == "use_memory":
        paper_list = []
        for item in mem:
            cleaned = _clean_paper(item)
            if cleaned:
                paper_list.append(cleaned)
    elif not isinstance(paper_list, list):
        paper_list = []
    else:
        # Clean paper_list items from LLM output
        cleaned_list = []
        for item in paper_list:
            if isinstance(item, dict):
                c = _clean_paper(item)
                if c:
                    cleaned_list.append(c)
        paper_list = cleaned_list

    # Auto-fallback: if paper_list is empty but intent requires papers, use conversation.memory
    # ONLY for content_summary (follow-up "Summarize them").
    # For metadata_list, empty paper_list means "all papers" — do NOT override.
    if not paper_list and intent == "content_summary" and mem:
        paper_list = []
        for item in mem:
            cleaned = _clean_paper(item)
            if cleaned:
                paper_list.append(cleaned)

    # ── Cap papers for content_summary to avoid context overflow ──
    # Full paper texts average ~11K chars each; 8 papers ≈ 48K chars ≈ 12K tokens
    # which fits comfortably in the Summary LLM's 65K context window and
    # keeps A2 (qwen2.5:14b) response time under 2 minutes.
    MAX_PAPERS_FOR_SUMMARY = 37
    #if intent == "content_summary" and len(paper_list) > MAX_PAPERS_FOR_SUMMARY:
    if intent == "content_summary":
        paper_list = paper_list[:MAX_PAPERS_FOR_SUMMARY]

    rw = str(obj.get("rewritten_query") or "").strip()
    # Fallback: if Router didn't set rewritten_query, use original query.
    if not rw and sys_query:
        rw = str(sys_query).strip()

    # ── Name-only query guard: if the user typed what looks like just a person's
    # name (e.g. "Helm, Mark", "M. Helm", "Dieterich") but the router misclassified
    # it as author_lookup / knowledge_retrieval → override to metadata_list.
    # Patterns detected: "Last, First", "X. Last", or 1-2 capitalized words.
    if intent in ("author_lookup", "knowledge_retrieval") and sys_query:
        q = str(sys_query).strip()
        has_comma = "," in q and len(q.split(",")) == 2
        has_dot_initials = bool(re.match(r"^[A-ZÀ-ÖØ-Ý]\.\s+\w{2,}$", q))
        one_or_two_words = (
            len(q.split()) in (1, 2)
            and not re.search(r"[.?!/]", q)
            and not any(
                w.lower() in q.lower()
                for w in (
                    "who",
                    "what",
                    "which",
                    "how",
                    "why",
                    "where",
                    "when",
                    "summarize",
                    "compare",
                    "group",
                    "find",
                    "list",
                    "show",
                    "experience",
                    "worked",
                    "using",
                    "studied",
                )
            )
        )
        if has_comma or has_dot_initials or one_or_two_words:
            intent = "paper_list"
            if not paper_list:
                # Use the query text as author filter
                paper_list = [{"authors": q, "title": "", "year": "", "journal": ""}]
                multi_author_bypass = True

    # ── "Find/Show papers by <name>" guard ─────────────────────────
    if sys_query:
        q = str(sys_query).strip().lower()
        # Check for "find papers by X", "show papers by X", "find publications by X"
        is_find_by = (
            q.startswith("find papers by ")
            or q.startswith("show papers by ")
            or q.startswith("find publications by ")
            or q.startswith("show publications by ")
            or q.startswith("find articles by ")
            or q.startswith("show articles by ")
        )
        if is_find_by:
            # Extract name after "by "
            parts = q.split(" by ", 1)
            if len(parts) == 2:
                name = parts[1].strip().rstrip(".,;")
                if name and len(name) >= 2:
                    intent = "paper_list"
                    # Keep as single entry — metadata_query handles comma-separated
                    # authors with OR matching, and the OR-hint in result_text tells
                    # the Metadata LLM to list all matches without AND filtering.
                    paper_list = [
                        {"authors": name, "title": "", "year": "", "journal": ""}
                    ]
                    # Deterministic author filter, single author or not - the
                    # Metadata LLM must not be allowed to re-synthesize this;
                    # bypass it so metadata_query.py's real match count/list
                    # (e.g. all 37 papers by this author) passes through as-is.
                    multi_author_bypass = True

    # ── "Identify: <name1>, <name2>, ..." guard ───────────────────
    # Catches multi-name identification queries like:
    #   "Identify: Mark Helm, Martin Hengesbach"
    #   "Identify Mark Helm, Martin Hengesbach"
    #   "Can you identify Mark Helm, Martin Hengesbach?"
    # Forces metadata_list with comma-separated authors (OR logic).
    if sys_query:
        q = str(sys_query).strip().lower()
        is_identify = (
            q.startswith("identify:")
            or q.startswith("identify ")
            or q.startswith("can you identify ")
            or q.startswith("which papers are by ")
        )
        if is_identify:
            # Extract the name portion: strip the prefix
            name_part = q
            for prefix in (
                "identify:",
                "identify ",
                "can you identify ",
                "which papers are by ",
            ):
                if name_part.startswith(prefix):
                    name_part = name_part[len(prefix) :]
                    break
            name_part = name_part.strip().rstrip(".,;?!")
            # Only override if it contains commas (multi-name) or looks like names
            if name_part and "," in name_part:
                # Normalize: ensure comma-space separation
                names = [n.strip() for n in name_part.split(",") if n.strip()]
                if len(names) >= 2:
                    intent = "paper_list"
                    # Split into separate entries so Metadata LLM sees individual authors
                    paper_list = [
                        {"authors": n, "title": "", "year": "", "journal": ""}
                        for n in names
                    ]

    # ── Multi-author bypass: skip Metadata LLM ────────────────────
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
        # Multi-author if: any entry has comma, OR multiple entries with authors
        has_comma = any("," in a for a in all_authors)
        if has_comma or len(all_authors) >= 2:
            multi_author_bypass = True

    # ── Collaboration analysis guard ───────────────────────────
    # Detects queries like "who collaborated most", "co-authors of X",
    # "collaboration network", "published together". Forces metadata_list
    # and passes collaboration_mode to metadata_query.py.
    collaboration_mode = ""
    if sys_query:
        q = str(sys_query).strip().lower()
        collab_markers = (
            "collaborat",
            "co-author",
            "coauthor",
            "co author",
            "co-authored",
            "coauthored",
            "published together",
            "publish together",
            "published with",
            "worked together",
            "work together",
            "co-autoren",
        )
        # Also match "share papers", "shared papers", "papers shared"
        has_share = bool(
            re.search(
                r"\bshare[ds]?\b.*\bpaper\b|\bpaper.*\bshare[ds]?\b|\bshare[ds]?\s*\?",
                q,
            )
        )
        if any(m in q for m in collab_markers) or has_share:
            intent = "paper_list"
            # Extract target author — match separators case-insensitively (q_lower)
            # but extract name preserving original case from sys_query
            q_orig = str(sys_query).strip()
            target = ""
            for sep in (
                "co-authors of ",
                "co-author of ",
                "collaborators of ",
                "coauthors of ",
                "collaborations of ",
                "collaboration of ",
            ):
                if sep in q:  # match lowercase
                    idx = q.index(sep)
                    target = q_orig[idx + len(sep) :].strip().rstrip(".,;?!")
                    break
            if not target:
                for sep in (
                    "co-authors with ",
                    "collaborated with ",
                    "collaborations with ",
                    "published with ",
                ):
                    if sep in q:
                        idx = q.index(sep)
                        target = q_orig[idx + len(sep) :].strip().rstrip(".,;?!")
                        break
            if not target:
                # "Which co-authors has Mark Helm published with?" → extract name
                m = re.search(
                    r"(?:co-authors?\s+(?:has\s+)?|coauthors?\s+(?:has\s+)?)([\w\s.-]+?)\s+(?:published\s+with|collaborated\s+with)",
                    q,
                )
                if m:
                    # Use the match position to extract from original case
                    start = m.start(1)
                    end = m.end(1)
                    target = q_orig[start:end].strip().rstrip(".,;?!")
            if not target:
                # Loose fallback: a name following "with" anywhere after a
                # collaboration marker, tolerating filler words in between
                # (e.g. "collaborated the most with X", "worked most closely
                # with X", "co-authored papers with X").
                m = re.search(
                    r"(?:collaborat\w*|co-?author\w*|publish\w*|work\w*)\b"
                    r"(?:(?!\bwith\b).){0,40}?\bwith\s+"
                    r"([\w.\-]+(?:\s+[\w.\-]+){0,3})",
                    q,
                )
                if m:
                    start, end = m.start(1), m.end(1)
                    candidate = q_orig[start:end].strip().rstrip(".,;?!")
                    # Guard against swallowing trailing question words/phrases
                    candidate = re.split(
                        r"\s+(?:the most|most often|the paper|papers?)\b",
                        candidate,
                    )[0].strip()
                    _generic_words = {
                        "anyone",
                        "someone",
                        "anybody",
                        "somebody",
                        "others",
                        "each other",
                        "them",
                        "him",
                        "her",
                        "anyone else",
                    }
                    if (
                        candidate
                        and len(candidate) > 1
                        and candidate.lower() not in _generic_words
                    ):
                        target = candidate
            if not target:
                # Possessive form: "X's collaborators" / "X's co-authors"
                m = re.search(
                    r"([\w.\-]+(?:\s+[\w.\-]+){0,3})'s\s+(?:collaborat\w*|co-?author\w*)",
                    q,
                )
                if m:
                    start, end = m.start(1), m.end(1)
                    target = q_orig[start:end].strip().rstrip(".,;?!")
            if not target:
                # Name BEFORE the marker: "who does Mark Helm collaborate
                # with?", "did Mark Helm co-author with anyone?"
                m = re.search(
                    r"(?:who\s+(?:does|did|has)\s+|does\s+|did\s+)"
                    r"([\w.\-]+(?:\s+[\w.\-]+){0,3}?)"
                    r"\s+(?:collaborate\w*|collaborated|co-?author\w*|publish\w*|work\w*)\b",
                    q,
                )
                if m:
                    start, end = m.start(1), m.end(1)
                    target = q_orig[start:end].strip().rstrip(".,;?!")
            if not target:
                # "How many collaborators/co-authors does X have?"
                m = re.search(
                    r"(?:collaborators?|co-?authors?)\s+does\s+"
                    r"([\w.\-]+(?:\s+[\w.\-]+){0,3})\s+have\b",
                    q,
                )
                if m:
                    start, end = m.start(1), m.end(1)
                    target = q_orig[start:end].strip().rstrip(".,;?!")
            # ── Dual-author detection ───────────────────────────
            # Patterns: "co-authored by X and Y", "X and Y collaboration",
            # "papers co-authored by X and Y", "do X and Y share papers?"
            dual_target = ""
            dual_patterns = [
                # Specific prefix patterns first (avoid ambiguous matching)
                r"collaborat\w*\s+between\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)",
                r"co[- ]?authored?\s+by\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)",
                r"how\s+many\s+papers\s+(?:do|have)\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:share|co[- ]?author|publish)",
                r"([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+collaborat",
                r"do\s+([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:share|have|co[- ]?author)",
                # Generic "X and Y verb" — LAST to avoid false matches
                r"([\w.-]+(?:\s+[\w.-]+)?)\s+and\s+([\w.-]+(?:\s+[\w.-]+)?)\s+(?:published|co[- ]?authored|share|shared|joint)",
            ]
            for pattern in dual_patterns:
                m = re.search(pattern, q)
                if m:
                    n1 = q_orig[m.start(1) : m.end(1)].strip().rstrip(".,;?!")
                    n2 = q_orig[m.start(2) : m.end(2)].strip().rstrip(".,;?!")
                    if n1 and n2 and len(n1) > 1 and len(n2) > 1:
                        dual_target = f"{n1}|{n2}"
                    break

            collaboration_mode = (
                dual_target if dual_target else (target if target else "all")
            )
            paper_list = []
            multi_author_bypass = True

    # ── "What else" follow-up guard ────────────────────────────
    # Detects "what else did X publish?" follow-up queries.
    # The LLM Router (qwen2.5:14b) ignores the prompt rule for this,
    # so we override at code level. Extracts author from conversation.memory
    # (previous turn) for pronoun queries, or uses explicit name.
    if sys_query:
        q = str(sys_query).strip().lower()
        is_what_else = (
            q.startswith("what else ")
            or q.startswith("anything else ")
            or "what else has " in q
            or "what else did " in q
        )
        if is_what_else and mem:
            # Try to extract author from conversation.memory (previous turn)
            prev_authors = set()
            for item in mem:
                if isinstance(item, dict):
                    a = str(item.get("authors", "")).strip()
                    if a:
                        # Take unique authors (usually just one if prev query was author-filtered)
                        prev_authors.add(a)
            if prev_authors:
                # Use the author(s) from the previous turn
                intent = "metadata_list"
                paper_list = [
                    {
                        "authors": list(prev_authors)[0],
                        "title": "",
                        "year": "",
                        "journal": "",
                    }
                ]
                # Same deterministic-filter reasoning as the other guards above.
                multi_author_bypass = True
            # else: fall through to router's classification (no memory to work with)

    # ── "Which authors published in <year>?" guard ─────────────────
    # Router tends to pattern-match "Which authors...?" against the
    # entity_lookup template ("Which <entities>...?"), even though this is
    # a plain metadata filter (year), not content-derived entity extraction.
    if sys_query:
        q = str(sys_query).strip().lower()
        m = re.search(
            r"(?:which|what)\s+(?:authors?|researchers?)\s+(?:have\s+)?published\s+in\s+((?:19|20)\d{2})"
            r"|who\s+(?:has\s+)?published\s+in\s+((?:19|20)\d{2})"
            r"|(?:authors?|researchers?)\s+(?:who|that)\s+published\s+in\s+((?:19|20)\d{2})",
            q,
        )
        if m:
            year_val = next(g for g in m.groups() if g)
            intent = "metadata_list"
            list_mode = "authors"
            paper_list = [
                {"authors": "", "title": "", "year": year_val, "journal": ""}
            ]

    # ── Metadata-only follow-up guard ───────────────────────────
    # "When did this paper get published?", "What journal is this in?",
    # "Who wrote this?" — these ask about METADATA of an already-referenced
    # paper, not its content. No full-text fetch is needed, so this must
    # NOT fall into content_summary (which triggers Fetch Full Paper for
    # every paper in memory just to answer a one-field question).
    if sys_query and mem:
        q = str(sys_query).strip().lower()
        metadata_followup_markers = (
            "when did this paper",
            "when was this paper",
            "when did the paper",
            "when was it published",
            "when was this published",
            "what year was this",
            "what journal is this",
            "which journal is this",
            "what journal was this published in",
            "who wrote this",
            "who are the authors of this",
            "who authored this",
            "wann wurde das veröffentlicht",
            "wann wurde dies veröffentlicht",
            "wann wurde der artikel veröffentlicht",
        )
        if any(marker in q for marker in metadata_followup_markers):
            content_intent_markers = (
                "summarize",
                "summarise",
                "compare",
                "methods",
                "method",
                "findings",
                "results",
                "analyze",
                "analyse",
                "discuss",
                "explain",
                "key points",
                "abstract",
                "conclusion",
                "what did they",
                "how did they",
                "zusammenfass",
            )
            is_mixed_query = any(m in q for m in content_intent_markers)
            if not is_mixed_query:
                from_memory = []
                for item in mem:
                    cleaned = _clean_paper(item)
                    if cleaned:
                        from_memory.append(cleaned)
                if from_memory:
                    intent = "metadata_list"
                    paper_list = from_memory
            # else: query also asks about content — fall through so
            # content_summary (and the full-text fetch it needs) still fires.

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
    }