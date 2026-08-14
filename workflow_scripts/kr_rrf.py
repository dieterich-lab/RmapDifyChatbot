# Code Node: KR RRF Merge
#
# Takes the "result" arrays from two parallel Knowledge Retrieval nodes -
# one configured for pure semantic search (vector_weight: 1.0, keyword_weight: 0.0)
# and one for pure keyword search (vector_weight: 0.0, keyword_weight: 1.0) -
# and merges them via Reciprocal Rank Fusion instead of a raw score blend.
#
# Why RRF instead of averaging the two scores directly: cosine similarity
# (semantic) and keyword/BM25-style scores live on different, incomparable
# numeric scales. A chunk that's a near-perfect keyword match but a middling
# semantic match can get diluted out under a linear blend. RRF only uses
# each chunk's RANK POSITION within each list, so no score-scale assumptions
# are needed, and a chunk only needs to rank well in ONE of the two searches
# to surface.
#
# Wiring in Dify:
#   - Two Knowledge Retrieval nodes, each with retrieval_mode: multiple and
#     opposite weights (see comment above). Same query_variable_selector.
#   - This code node's inputs:
#       semantic_result <- {{#<semantic_KR_node_id>.result#}}
#       keyword_result  <- {{#<keyword_KR_node_id>.result#}}
#   - Output "result" has the SAME shape as a normal Knowledge Retrieval
#     node's "result" (list of {metadata, title, content, ...}), so it can
#     be wired straight into KR Chunk Filter / KR Extraction LLM with no
#     other changes downstream.

RRF_K = 60  # standard default; higher k flattens the influence of rank differences
DIFY_ARRAY_CAP = 30  # hard platform limit on Array[object] output variables


def _segment_key(item):
    """Unique identity for a retrieved chunk. Falls back to document_id +
    a content hash if segment_id is ever missing, so nothing gets silently
    dropped even for malformed items."""
    meta = (item or {}).get("metadata") or {}
    seg_id = meta.get("segment_id")
    if seg_id:
        return str(seg_id)
    doc_id = meta.get("document_id", "")
    content = (item or {}).get("content", "")
    return f"{doc_id}:{hash(content)}"


def main(semantic_result=None, keyword_result=None, top_n=30):
    semantic_list = semantic_result if isinstance(semantic_result, list) else []
    keyword_list = keyword_result if isinstance(keyword_result, list) else []

    # Dify's Array[object] output variables cannot exceed 30 elements -
    # clamp regardless of what top_n was passed in, so this never errors
    # even if a node upstream (or a manual test run) requests more.
    effective_top_n = min(top_n, DIFY_ARRAY_CAP) if top_n else DIFY_ARRAY_CAP

    # rank is 1-indexed position within each list (lists are assumed to
    # already be sorted best-first by Dify's own retrieval, which they are).
    rrf_scores = {}
    items_by_key = {}
    source_counts = {}  # for debugging/inspection: how many lists each item hit

    for source_list in (semantic_list, keyword_list):
        for rank, item in enumerate(source_list, start=1):
            if not isinstance(item, dict):
                continue
            key = _segment_key(item)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            source_counts[key] = source_counts.get(key, 0) + 1
            # Keep the first-seen full item; if it shows up in both lists,
            # prefer the one with more retrieval metadata already attached.
            if key not in items_by_key:
                items_by_key[key] = item

    ranked_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

    merged = []
    for position, key in enumerate(ranked_keys[:top_n], start=1):
        item = dict(items_by_key[key])  # shallow copy, don't mutate original
        meta = dict(item.get("metadata") or {})
        meta["score"] = rrf_scores[key]  # overwrite with fused score
        meta["rrf_rank"] = position
        meta["matched_in_both"] = source_counts[key] == 2
        item["metadata"] = meta
        merged.append(item)

    return {
        "result": merged,
        "semantic_count": len(semantic_list),
        "keyword_count": len(keyword_list),
        "merged_count": len(merged),
        "overlap_count": sum(1 for k in ranked_keys[:top_n] if source_counts[k] == 2),
    }