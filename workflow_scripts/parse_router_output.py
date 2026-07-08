# Code Node: Parse Router Output
# Node ID: 1778800001033

import json, re

# Domain synonyms for recall-boosting in author_lookup / entity_lookup
_QUERY_EXPANSIONS = [
    # (trigger phrase, expansion terms)
    ("tRNA modification", "tRNA maturation tRNA processing tRNA modification enzyme anticodon modification"),
    ("queuosine", "Q modification Q detection queuosinylation QTRT1 QTRT2 TGT"),
    ("m6A", "N6-methyladenosine m6A methylation m6A detection epitranscriptome"),
    ("RNA modification", "RNA modification epitranscriptome RNA methylation modified nucleotide"),
]

def _expand_query(query, intent):
    """Expand query with domain synonyms for author_lookup only."""
    if intent != 'author_lookup':
        return query
    q = str(query or '').strip()
    if not q:
        return q
    q_lower = q.lower()
    extra_terms = []
    for trigger, expansion in _QUERY_EXPANSIONS:
        if trigger.lower() in q_lower:
            extra_terms.append(expansion)
    if extra_terms:
        return q + ' ' + ' '.join(extra_terms)
    return q

def _clean_paper(item):
    if not isinstance(item, dict):
        return None
    obj = {
        'title': str(item.get('title') or '').strip(),
        'authors': str(item.get('authors') or item.get('author') or '').strip(),
        'year': str(item.get('year') or '').strip(),
        'journal': str(item.get('journal') or '').strip(),
    }
    doc_id = str(item.get('doc_id') or '').strip()
    if doc_id:
        obj['doc_id'] = doc_id
    return obj if any(obj.values()) else None

def main(router_text=None, conversation_memory=None):
    text = str(router_text or '').strip()
    # Strip <think> tags
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    # Strip markdown fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text).strip()
    # Find JSON object
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {'intent': 'knowledge_retrieval', 'paper_list': [], 'rewritten_query': ''}
    try:
        obj = json.loads(m.group())
    except Exception:
        return {'intent': 'knowledge_retrieval', 'paper_list': [], 'rewritten_query': ''}

    intent = str(obj.get('intent', '')).strip()
    if intent not in ('metadata_list', 'content_summary', 'knowledge_retrieval', 'author_lookup', 'entity_lookup'):
        intent = 'knowledge_retrieval'

    paper_list = obj.get('paper_list')
    mem = conversation_memory if isinstance(conversation_memory, list) else []

    # If paper_list is the string "use_memory", populate from conversation.memory
    if paper_list == 'use_memory':
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
    if not paper_list and intent in ('metadata_list', 'content_summary') and mem:
        paper_list = []
        for item in mem:
            cleaned = _clean_paper(item)
            if cleaned:
                paper_list.append(cleaned)

    rw = str(obj.get('rewritten_query') or '').strip()
    query_for_expansion = rw if rw else str(obj.get('rewritten_query', ''))
    expanded = _expand_query(query_for_expansion, intent)
    return {'intent': intent, 'paper_list': paper_list, 'paper_count': len(paper_list), 'rewritten_query': rw, 'expanded_query': expanded}
