import os
import sys
import json
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from evaluator import evaluate_program

# Candidate 1: Baseline Simple Term Frequency Match
CANDIDATE_GEN_0 = """import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
"""

# Candidate 2: Generation 5 Hillclimb Mutation - Weighted TF + Title Prefix Boost
CANDIDATE_GEN_5 = """import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # EVOLVE-BLOCK-START: rerank_algorithm
    query_terms = [t.lower() for t in query.split() if len(t) > 2]
    scored_items = []
    
    for item in raw_results:
        doc = item.get("document", {})
        derived = doc.get("derivedStructData", {})
        struct = doc.get("structData", {})
        
        title = (derived.get("title") or struct.get("title") or "").lower()
        snippets = derived.get("snippets", [])
        snippet_text = (snippets[0].get("snippet", "") if snippets else "").lower()
        
        score = 0.0
        for term in query_terms:
            if term in title:
                score += 5.0
            if title.startswith(term):
                score += 3.0
            score += snippet_text.count(term) * 1.5
            
        scored_items.append((score, item))
        
    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items]
    # EVOLVE-BLOCK-END: rerank_algorithm
"""

# Candidate 3: Generation 12 Hillclimb - BM25 Saturated Scoring + Exact Match Hybrid
CANDIDATE_GEN_12 = """import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # EVOLVE-BLOCK-START: rerank_algorithm
    query_clean = query.strip().lower()
    query_terms = set(query_clean.split())
    scored_items = []
    
    for item in raw_results:
        doc = item.get("document", {})
        derived = doc.get("derivedStructData", {})
        struct = doc.get("structData", {})
        
        title = (derived.get("title") or struct.get("title") or "").lower()
        snippets = derived.get("snippets", [])
        snippet_text = (snippets[0].get("snippet", "") if snippets else "").lower()
        
        score = 0.0
        
        # 1. Exact query phrase match in title (Highest relevance signal)
        if query_clean in title:
            score += 15.0
            
        # 2. Term frequency saturation (BM25 style term scaling)
        for term in query_terms:
            title_count = title.count(term)
            snippet_count = snippet_text.count(term)
            
            # Saturated log scaling to prevent keyword stuffing
            score += (math.log1p(title_count) * 6.0) + (math.log1p(snippet_count) * 2.0)
            
        scored_items.append((score, item))
        
    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items]
    # EVOLVE-BLOCK-END: rerank_algorithm
"""

# Candidate 4: Generation 20 (Pre-Commit Staging Staged Candidate) - Multi-Source Field Aware Reranker
CANDIDATE_GEN_20 = """import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
"""

def run_simulation():
    benchmark_path = os.path.join(CURRENT_DIR, "benchmark_data.json")
    
    print("==================================================")
    print("   AlphaEvolve Reranking Evolutionary Search Simulation")
    print("==================================================")
    
    candidates = [
        ("Generation 0 (Baseline Term Frequency)", CANDIDATE_GEN_0),
        ("Generation 5 (TF + Title Prefix Mutation)", CANDIDATE_GEN_5),
        ("Generation 12 (BM25 Saturation + Phrase Match)", CANDIDATE_GEN_12),
        ("Generation 20 (Pre-Commit Staged Hillclimbed Winner)", CANDIDATE_GEN_20)
    ]
    
    trajectory = []
    for gen_name, code in candidates:
        eval_result = evaluate_program(code, benchmark_path)
        trajectory.append({
            "generation": gen_name,
            "score": eval_result["score"],
            "insights": eval_result["insights"]
        })
        print(f"\n📊 {gen_name}:")
        print(f"   • Overall Score: {eval_result['score']}")
        for ins in eval_result["insights"]:
            print(f"   • {ins['label'].capitalize()}: {ins['text']}")
            
    print("\n==================================================")
    print("   Evolutionary Search Trajectory Summary")
    print("==================================================")
    for t in trajectory:
        print(f"Gen: {t['generation']:<50} ---> Fitness Score: {t['score']}")
    print("==================================================")

if __name__ == "__main__":
    run_simulation()
