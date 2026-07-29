import argparse
import ast
import json
import os
import sys
import time

def evaluate_program(code: str, benchmark_path: str) -> dict:
    """Three-Tier AlphaEvolve Evaluator following official DeepMind specifications."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("sys", "os", "subprocess", "inspect"):
                        return {"score": None, "insights": [{"label": "validation", "text": f"Forbidden module: {alias.name}"}]}
    except SyntaxError as syntax_err:
        return {"score": None, "insights": [{"label": "validation", "text": f"Syntax error: {syntax_err}"}]}

    namespace = {}
    try:
        exec(compile(code, "initial_program.py", "exec"), namespace)
    except Exception as exec_err:
        return {"score": None, "insights": [{"label": "validation", "text": f"Execution error: {exec_err}"}]}

    rerank_fn = namespace.get("rerank_documents")
    if not callable(rerank_fn):
        return {"score": None, "insights": [{"label": "validation", "text": "Missing rerank_documents() function"}]}

    if not os.path.exists(benchmark_path):
        return {"score": None, "insights": [{"label": "validation", "text": "Benchmark dataset file missing"}]}

    with open(benchmark_path) as f:
        benchmark_data = json.load(f)

    verif_passed = 0
    verif_total = len(benchmark_data)
    
    for item in benchmark_data:
        try:
            res = rerank_fn(item["query"], item["raw_results"])
            if isinstance(res, list) and len(res) == len(item["raw_results"]):
                verif_passed += 1
        except Exception:
            pass

    verif_ratio = verif_passed / max(verif_total, 1)
    if verif_ratio < 1.0:
        return {
            "score": verif_ratio * 0.4,
            "insights": [{"label": "verification", "text": f"{verif_passed}/{verif_total} structural checks passed"}]
        }

    correct_top_rank = 0
    total_queries = len(benchmark_data)
    
    start_time = time.perf_counter()
    for item in benchmark_data:
        reranked = rerank_fn(item["query"], item["raw_results"])
        top_doc = reranked[0].get("document", {}).get("derivedStructData", {}).get("title", "")
        if top_doc == item["target_top_title"]:
            correct_top_rank += 1
            
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    precision = correct_top_rank / max(total_queries, 1)
    latency_penalty = min(0.2, (elapsed_ms / 50.0))
    
    score = max(0.0, min(1.0, 0.5 + (precision * 0.4) - latency_penalty))
    
    return {
        "score": round(score, 4),
        "insights": [
            {"label": "precision", "text": f"{precision*100:.1f}% ({correct_top_rank}/{total_queries})"},
            {"label": "latency_ms", "text": f"{elapsed_ms:.2f}ms"},
            {"label": "verification", "text": f"{verif_passed}/{verif_total} passed"}
        ]
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--program-dir", required=True)
    args = parser.parse_args()

    program_path = os.path.join(args.program_dir, "initial_program.py")
    benchmark_path = os.path.join(args.program_dir, "benchmark_data.json")

    if not os.path.exists(program_path):
        res = {"score": None, "insights": [{"label": "error", "text": "initial_program.py missing"}]}
    else:
        with open(program_path) as f:
            code = f.read()
        res = evaluate_program(code, benchmark_path)

    with open(args.output_file, "w") as f:
        json.dump(res, f, indent=2)
        
    print(f"Evaluator Execution Finished. Result: {res}")

if __name__ == "__main__":
    main()
