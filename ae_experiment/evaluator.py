import argparse
import ast
import json
import os
import time


ALLOWED_MODULES = {"math", "typing", "re", "collections"}
FORBIDDEN_NAMES = {"eval", "exec", "open", "compile", "__import__", "globals", "locals", "getattr", "setattr", "delattr", "breakpoint"}
FORBIDDEN_ATTRS = {"__subclasses__", "__globals__", "__code__", "__class__", "__bases__", "__mro__", "__builtins__"}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root_mod = name.split(".")[0]
    if root_mod not in ALLOWED_MODULES:
        raise ImportError(f"Import of '{name}' is strictly forbidden by security policy")
    return __import__(name, globals, locals, fromlist, level)


SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "issubclass": issubclass, "iter": iter,
    "len": len, "list": list, "map": map, "max": max, "min": min,
    "next": next, "range": range, "round": round, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
    "zip": zip, "True": True, "False": False, "None": None,
    "__import__": _safe_import
}


def validate_code_security(code: str) -> str | None:
    """Strict AST validator ensuring candidate programs cannot execute unsafe operations."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod not in ALLOWED_MODULES:
                    return f"Forbidden module import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod not in ALLOWED_MODULES:
                    return f"Forbidden module import from: {node.module}"
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                return f"Forbidden identifier: {node.id}"
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                return f"Forbidden attribute access: {node.attr}"

    return None


def evaluate_program(code: str, benchmark_path: str) -> dict:
    """Three-Tier AlphaEvolve Evaluator with strict AST security enforcement."""
    sec_err = validate_code_security(code)
    if sec_err:
        return {"score": None, "insights": [{"label": "validation", "text": f"Security check failed: {sec_err}"}]}

    namespace = {"__builtins__": SAFE_BUILTINS}
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
        top_doc_dict = reranked[0].get("document", {})
        top_doc = (
            top_doc_dict.get("derivedStructData", {}).get("title")
            or top_doc_dict.get("structData", {}).get("title", "")
        )
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
