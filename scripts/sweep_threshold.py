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
import argparse


from src.evaluation import evaluate_suite, load_queries
from src.embedding import DEFAULT_TOP_K


THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
OUTPUT_DIR = Path("data/eval")
SUMMARY_PATH = OUTPUT_DIR / "sweep_summary.json"


def run_sweep(queries: list[dict], thresholds: list[float]) -> list[dict]:
    """Run evaluate_suite at each threshold and collect metrics."""
    rows = []
    for t in thresholds:
        print(f"  Evaluating at threshold {t:.2f} ...")
        results = evaluate_suite(queries, top_k=DEFAULT_TOP_K, threshold=t)
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


def save_sweep(rows: list[dict], path: Path, thresholds: list[float], suite: Path) -> None:
    """Persist sweep results with metadata."""
    output = {
        "run_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suite": str(suite),
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
    parser = argparse.ArgumentParser(description="Threshold sweep")
    parser.add_argument(
        "--suite",
        type=Path,
        default=OUTPUT_DIR / "query_suite.json",
        help="Path to the query suite JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the summary (defaults to sweep_summary_<suite>.json)",
    )
    args = parser.parse_args()

    out_path = args.out or OUTPUT_DIR / f"sweep_summary_{args.suite.stem}.json"

    print(f"Loading query suite from {args.suite} ...")
    queries = load_queries(args.suite)
    print(f"Loaded {len(queries)} queries. Running sweep across {len(THRESHOLDS)} thresholds.")
    print(f"Each run embeds {len(queries)} queries — this will take a few minutes.\n")

    rows = run_sweep(queries, THRESHOLDS)
    print_table(rows)
    save_sweep(rows, out_path, THRESHOLDS, args.suite)

    print("\nNo auto-recommendation — the recon showed no clean separation.")
   

    return rows


if __name__ == "__main__":
    main()