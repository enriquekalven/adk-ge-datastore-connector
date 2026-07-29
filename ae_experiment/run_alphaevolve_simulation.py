import os
import sys
import json
import time
from ae_experiment.evaluator import evaluate_program

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

# Candidate 3: Generation 12 Hillclimb Winner - BM25 Saturated Scoring + Exact Match Hybrid
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

def run_simulation():
    benchmark_path = os.path.join(os.path.dirname(__file__), "benchmark_data.json")
    
    print("==================================================")
    print("   AlphaEvolve Reranking Evolutionary Search Simulation")
    print("==================================================")
    
    candidates = [
        ("Generation 0 (Baseline Term Frequency)", CANDIDATE_GEN_0),
        ("Generation 5 (TF + Title Prefix Mutation)", CANDIDATE_GEN_5),
        ("Generation 12 (BM25 Saturation + Phrase Match Winner)", CANDIDATE_GEN_12)
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
        print(f"Gen: {t['generation']} ---> Fitness Score: {t['score']}")
    print("==================================================")

if __name__ == "__main__":
    run_simulation()
