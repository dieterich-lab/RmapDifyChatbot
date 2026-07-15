# Code Node: Parse Router Output
# Node ID: 1778800001033

import json
import re

# ── Broad-listing query patterns → route to metadata_list ──
_BROAD_LISTING_PATTERNS = [
    # English
    r"\bfind\s+all\b",
    r"\blist\s+all\b",
    r"\b(all|every)\s+(research\s+)?(paper|article|publication|document)s?\b",
    r"\b(all|every)\s+(author|researcher|scientist)s?\b",
    r"\bwho\s+are\s+(all\s+)?(the\s+)?(author|researcher|scientist)s?\b",
    r"\bwhat\s+(paper|article|publication|document)s?\s+(are|exist|do\s+we\s+have)\b",
    # German
    r"\bfinde\s+alle\b",
    r"\bliste\s+alle\b",
    r"\balle\s+(Forschungs)?(Paper|Artikel|Publikation|Dokument)e\b",
    r"\balle\s+(Autor|Forscher|Wissenschaftler|Author)innen?\b",
    r"\bwelche\s+(Autor|Forscher|Wissenschaftler|Author)innen?\s+(gibt|existieren|haben\s+wir)\b",
    r"\bwelche\s+(Paper|Artikel|Publikation|Dokument)e\s+(gibt|existieren|haben\s+wir)\b",
]


def _is_broad_listing_query(query: str) -> bool:
    q = str(query or "").lower().strip()
    if len(q) < 5:
        return False
    for pat in _BROAD_LISTING_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return True
    return False


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
        return {
            "intent": "knowledge_retrieval",
            "paper_list": [],
            "rewritten_query": "",
        }
    try:
        obj = json.loads(m.group())
    except Exception:
        return {
            "intent": "knowledge_retrieval",
            "paper_list": [],
            "rewritten_query": "",
        }

    intent = str(obj.get("intent", "")).strip()
    if intent not in (
        "metadata_list",
        "content_summary",
        "knowledge_retrieval",
        "author_lookup",
        "entity_lookup",
    ):
        intent = "knowledge_retrieval"

    # ── Override: broad listing queries → metadata_list ──
    query = str(sys_query or "").strip()
    if intent == "knowledge_retrieval" and _is_broad_listing_query(query):
        intent = "metadata_list"
        obj["paper_list"] = []  # empty → Metadata Query lists ALL

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
    if not paper_list and intent in ("metadata_list", "content_summary") and mem:
        paper_list = []
        for item in mem:
            cleaned = _clean_paper(item)
            if cleaned:
                paper_list.append(cleaned)

    rw = str(obj.get("rewritten_query") or "").strip()
    return {
        "intent": intent,
        "paper_list": paper_list,
        "paper_count": len(paper_list),
        "rewritten_query": rw,
    }
