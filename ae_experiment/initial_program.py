import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reranks and filters Discovery Engine search results to maximize relevance and information density.
    
    Args:
        query: User search query string.
        raw_results: List of raw document objects returned by Discovery Engine API.
        
    Returns:
        List of reranked document objects sorted by relevance.
    """
    # EVOLVE-BLOCK-START: rerank_algorithm
    query_terms = set(query.lower().split())
    scored_items = []
    
    for item in raw_results:
        doc = item.get("document", {})
        derived = doc.get("derivedStructData", {})
        struct = doc.get("structData", {})
        
        title = (derived.get("title") or struct.get("title") or "").lower()
        snippets = derived.get("snippets", [])
        snippet_text = (snippets[0].get("snippet", "") if snippets else "").lower()
        
        text_corpus = f"{title} {snippet_text}"
        
        matches = sum(1 for term in query_terms if term in text_corpus)
        title_matches = sum(1 for term in query_terms if term in title)
        
        score = matches + (title_matches * 2.0)
        scored_items.append((score, item))
        
    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items]
    # EVOLVE-BLOCK-END: rerank_algorithm
