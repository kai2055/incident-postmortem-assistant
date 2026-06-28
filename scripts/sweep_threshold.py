"""
Threshold sweep for RELEVANCE_THRESHOLD tuning.

Runs the query suite across candidate thresholds and reports the trade-off
between hit rate, MRR, and decline rate. The output is a table and a JSON
artifact that becomes evidence for the threshold decision in ADR-11.

Usage:
    python scripts/sweep_threshold.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.evaluation import evaluate_suite, load_queries


THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
OUTPUT_DIR = Path("data/eval")
SUMMARY_PATH = OUTPUT_DIR / "sweep_summary.json"


def run_sweep(queries: list[dict], thresholds: list[float]) -> list[dict]:
    """Run evaluate_suite at each threshold and collect metrics."""
    rows = []
    for t in thresholds:
        print(f"  Evaluating at threshold {t:.2f} ...")
        results = evaluate_suite(queries, top_k=5, threshold=t)
        o = results["overall"]
        rows.append({
            "threshold": t,
            "hit_rate": o.get("hit_rate"),
            "mrr": o.get("mrr"),
            "decline_rate": o.get("decline_rate"),
        })
    return rows


def print_table(rows: list[dict]) -> None:
    """Print a formatted table of sweep results."""
    header = f"{'Threshold':>10} | {'Hit Rate':>10} | {'MRR':>10} | {'Decline Rate':>14}"
    line = "-" * len(header)
    
    print("\n" + "=" * len(header))
    print("THRESHOLD SWEEP RESULTS")
    print("=" * len(header))
    print(header)
    print(line)
    
    for r in rows:
        print(f"{r['threshold']:>10.2f} | {r['hit_rate']:>10.3f} | {r['mrr']:>10.3f} | {r['decline_rate']:>14.3f}")
    
    print(line)


def save_sweep(rows: list[dict], path: Path, thresholds: list[float]) -> None:
    """Persist sweep results with metadata."""
    output = {
        "run_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thresholds_swept": thresholds,
            "total_runs": len(rows),
        },
        "sweep_results": rows,
    }
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSweep summary saved to {path}")


def main():
    print("Loading query suite ...")
    queries = load_queries()
    print(f"Loaded {len(queries)} queries. Running sweep across {len(THRESHOLDS)} thresholds.")
    print(f"Each run embeds {len(queries)} queries — this will take a few minutes.\n")
    
    rows = run_sweep(queries, THRESHOLDS)
    print_table(rows)
    save_sweep(rows, SUMMARY_PATH, THRESHOLDS)
    
    print("\nNo auto-recommendation — the recon showed no clean separation.")
    print("Read the table and pick the tradeoff that fits your reliability story.")
    
    return rows


if __name__ == "__main__":
    main()