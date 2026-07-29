"""
Run the evaluation N times and record the spread.

Single-run baselines can't show how much the numbers naturally move run-to-run.
This runs the eval repeatedly, saves each run, and reports mean/min/max/stdev
per metric — so thresholds can be set from observed noise, not guesses.

Writes to data/eval/stability/ ONLY. Never touches baseline.json.

Usage:
    python -m scripts.stability --layer 1 --runs 10
    python -m scripts.stability --layer 2 --runs 3
"""

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

STABILITY_DIR = Path("data/eval/stability")


def run_layer1() -> dict:
    from src.embedding import DEFAULT_TOP_K, RELEVANCE_THRESHOLD
    from src.evaluation import evaluate_suite, load_queries
    results = evaluate_suite(load_queries(), top_k=DEFAULT_TOP_K, threshold=RELEVANCE_THRESHOLD)
    return results["overall"]


def run_layer2() -> dict:
    from scripts.score_layer2 import aggregate, run_suite_frozen
    from src.agent import build_diagnostic_graph_from_symptoms
    with open("data/eval/layer2_suite.json") as f:
        suite = {q["id"]: q for q in json.load(f)}
    with open("data/eval/layer2_symptoms.json") as f:
        frozen = json.load(f)["entries"]
    graph = build_diagnostic_graph_from_symptoms()
    tmp = STABILITY_DIR / "_layer2_tmp.json"
    ordered = run_suite_frozen(frozen, suite, graph, tmp, Path("data/eval/layer2_suite.json"))
    return aggregate(ordered)


LAYER1_METRICS = ["hit_rate", "mrr", "section_accuracy", "decline_rate",
                  "filter_precision", "filter_recall", "filter_exact_match_rate"]
LAYER2_METRICS = ["top1_accuracy", "any_hit_rate", "noise_rate", "decline_rate",
                  "mean_candidates", "grounding_violations", "mean_iterations"]


def summarize(runs: list[dict], metrics: list[str]) -> dict:
    out = {}
    for m in metrics:
        vals = [r[m] for r in runs if r.get(m) is not None]
        if not vals:
            out[m] = None
            continue
        out[m] = {
            "mean": round(statistics.mean(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "stdev": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
            "n": len(vals),
        }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", type=int, choices=[1, 2], required=True)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    STABILITY_DIR.mkdir(parents=True, exist_ok=True)
    runner = run_layer1 if args.layer == 1 else run_layer2
    metrics = LAYER1_METRICS if args.layer == 1 else LAYER2_METRICS

    runs = []
    for i in range(1, args.runs + 1):
        print(f"[{i}/{args.runs}] running layer {args.layer} ...")
        t0 = time.time()
        result = runner()
        result["_seconds"] = round(time.time() - t0, 1)
        runs.append(result)
        with open(STABILITY_DIR / f"layer{args.layer}_run_{i:03d}.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"    {result['_seconds']}s")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layer": args.layer,
        "runs": len(runs),
        "summary": summarize(runs, metrics),
    }
    with open(STABILITY_DIR / f"layer{args.layer}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary ({len(runs)} runs), layer {args.layer}:")
    for m, s in summary["summary"].items():
        if s:
            print(f"  {m:24} mean {s['mean']:.4f}  range [{s['min']:.4f}, {s['max']:.4f}]  stdev {s['stdev']:.4f}")
    print(f"\nSaved to data/eval/stability/layer{args.layer}_summary.json")


if __name__ == "__main__":
    main()