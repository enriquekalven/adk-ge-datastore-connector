import math
from typing import Any


def rerank_documents(query: str, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reranks and filters Discovery Engine search results to maximize relevance and information density.
    
    Args:
        query: User search query string.
        raw_results: List of raw document objects returned by Discovery Engine API.
        
    Returns:
        List of reranked document objects sorted by relevance.
    """
    # EVOLVE-BLOCK-START: rerank_algorithm
    query_clean = query.strip().lower()
    query_terms = [t for t in query_clean.split() if len(t) > 1]
    if not query_terms:
        return raw_results

    scored_items = []
    for item in raw_results:
        doc = item.get("document", {})
        derived = doc.get("derivedStructData", {})
        struct = doc.get("structData", {})

        title = (derived.get("title") or struct.get("title") or "").lower()
        snippets = derived.get("snippets", [])
        snippet_text = " ".join([s.get("snippet", "") for s in snippets]).lower()
        desc = (struct.get("description") or "").lower()
        url = (derived.get("link") or struct.get("html_url") or "").lower()
        extra = " ".join([str(v) for v in struct.values()]).lower()

        score = 0.0

        # 1. Exact phrase match in title or URL
        if query_clean in title:
            score += 25.0
        if query_clean in desc or query_clean in url:
            score += 15.0

        # 2. Term overlap & BM25 log saturation across fields
        matched_terms = 0
        for term in query_terms:
            t_in_title = title.count(term)
            t_in_desc = desc.count(term)
            t_in_snip = snippet_text.count(term)
            t_in_url = url.count(term)
            t_in_extra = extra.count(term)

            if t_in_title or t_in_desc or t_in_snip or t_in_url or t_in_extra:
                matched_terms += 1

            score += (math.log1p(t_in_title) * 8.0)
            score += (math.log1p(t_in_desc) * 5.0)
            score += (math.log1p(t_in_snip) * 3.0)
            score += (math.log1p(t_in_url) * 4.0)
            score += (math.log1p(t_in_extra) * 2.0)

        # 3. Term coverage ratio bonus
        coverage_ratio = matched_terms / max(len(query_terms), 1)
        score += (coverage_ratio * 10.0)

        scored_items.append((score, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items]
    # EVOLVE-BLOCK-END: rerank_algorithm
