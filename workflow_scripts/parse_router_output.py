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
        "content_summary",
        "knowledge_retrieval",
        "author_lookup",
        "entity_lookup",
    ):
        intent = "knowledge_retrieval"

    # ── Read list_mode from router JSON (LLM-native, no regex) ──
    list_mode = str(obj.get("list_mode") or "").strip()
    if list_mode not in ("papers", "authors"):
        list_mode = "papers"  # default

    paper_list = obj.get("paper_list")
    mem = conversation_memory if isinstance(conversation_memory, list) else []

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
    MAX_PAPERS_FOR_SUMMARY = 8
    if intent == "content_summary" and len(paper_list) > MAX_PAPERS_FOR_SUMMARY:
        paper_list = paper_list[:MAX_PAPERS_FOR_SUMMARY]

    rw = str(obj.get("rewritten_query") or "").strip()

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
            intent = "metadata_list"
            if not paper_list:
                # Use the query text as author filter
                paper_list = [{"authors": q, "title": "", "year": "", "journal": ""}]

    # ── "Find/Show papers by <name>" guard ─────────────────────────
    if sys_query:
        q = str(sys_query).strip().lower()
        # Check for "find papers by X", "show papers by X", "find publications by X"
        is_find_by = (
            q.startswith("find papers by ") or q.startswith("show papers by ")
            or q.startswith("find publications by ") or q.startswith("show publications by ")
            or q.startswith("find articles by ") or q.startswith("show articles by ")
        )
        if is_find_by:
            # Extract name after "by "
            parts = q.split(" by ", 1)
            if len(parts) == 2:
                name = parts[1].strip().rstrip(".,;")
                if name and len(name) >= 2:
                    intent = "metadata_list"
                    paper_list = [{"authors": name, "title": "", "year": "", "journal": ""}]

    return {
        "intent": intent,
        "paper_list": paper_list,
        "paper_count": len(paper_list),
        "rewritten_query": rw,
        "list_mode": list_mode,
    }
