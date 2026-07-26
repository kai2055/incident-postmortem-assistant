"""
Layer 3 runner — produce the current-run numbers.

Re-indexes the corpus, runs both evals, and writes two current-run files in
the SAME shapes as the committed baselines so the comparator can diff them.

Does NOT compare and does NOT decide pass/fail. Its only job is: "what does
the system score right now?" Comparator and gate come next.

Usage:
    python -m scripts.run_layer3
"""

import subprocess
import sys
import time
from pathlib import Path

from scripts.score_layer2 import run_suite_frozen
from scripts.score_layer2 import save as save_layer2
from src.agent import build_diagnostic_graph_from_symptoms
from src.embedding import DEFAULT_TOP_K, RELEVANCE_THRESHOLD
from src.evaluation import evaluate_suite, load_queries, save_results

# Current-run outputs — mirror the baseline shapes, different filenames.
LAYER1_OUT = Path("data/eval/current_layer1.json")
LAYER2_OUT = Path("data/eval/current_layer2.json")
LAYER2_SUITE = Path("data/eval/layer2_suite.json")
LAYER2_SYMPTOMS = Path("data/eval/layer2_symptoms.json")


def reindex() -> None:
    """Rebuild the vector store so it matches the current corpus."""
    print("Re-indexing corpus...")
    subprocess.run([sys.executable, "-m", "src.embedding"], check=True)


def run_layer1() -> dict:
    print("\nRunning Layer 1 eval...")
    queries = load_queries()
    results = evaluate_suite(queries, top_k=DEFAULT_TOP_K, threshold=RELEVANCE_THRESHOLD)
    save_results(results, LAYER1_OUT, top_k=DEFAULT_TOP_K, threshold=RELEVANCE_THRESHOLD)
    return results


def run_layer2() -> list[dict]:
    print("\nRunning Layer 2 eval (frozen symptoms)...")
    import json
    with open(LAYER2_SUITE) as f:
        suite = {q["id"]: q for q in json.load(f)}
    with open(LAYER2_SYMPTOMS) as f:
        frozen = json.load(f)["entries"]
    graph = build_diagnostic_graph_from_symptoms()
    start = time.time()
    ordered = run_suite_frozen(frozen, suite, graph, LAYER2_OUT, LAYER2_SUITE)
    save_layer2(LAYER2_OUT, {r["id"]: r for r in ordered}, LAYER2_SUITE, time.time() - start)
    return ordered


def main():
    reindex()
    run_layer1()
    run_layer2()
    print("\nCurrent-run files written:")
    print(f"  {LAYER1_OUT}")
    print(f"  {LAYER2_OUT}")


if __name__ == "__main__":
    main()