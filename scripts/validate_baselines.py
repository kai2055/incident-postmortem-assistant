"""
Validate committed baselines in CI.

Cheap, deterministic, no Ollama/LLM. Confirms both baseline files load,
have the metrics the gate expects, and pass the gate when compared against
themselves (baseline vs. baseline must be all-zeros -> PASS). A failure
here means the committed artifacts are corrupt or malformed, not that the
system regressed.
"""

import sys
from pathlib import Path

from scripts.compare_layer3 import (
    load_layer1, load_layer2, diff_aggregates, diff_per_entry,
    LAYER1_METRICS, LAYER2_METRICS,
)
from scripts.gate_layer3 import run_gate

BASELINE_L1 = Path("data/eval/baseline.json")
BASELINE_L2 = Path("data/eval/layer2_baseline.json")


def main() -> None:
    # 1. Both files must load.
    l1 = load_layer1(BASELINE_L1)
    l2_overall, l2_pe = load_layer2(BASELINE_L2)

    # 2. Required metrics must be present.
    missing = [m for m in LAYER1_METRICS if m not in l1]
    missing += [f"layer2.{m}" for m in LAYER2_METRICS if m not in l2_overall]
    if missing:
        print(f"BASELINE INVALID: missing metrics: {missing}")
        sys.exit(1)

    # 3. Baseline compared against itself must pass the gate (all-zero diff).
    diff = {
        "layer1": {"aggregates": diff_aggregates(l1, l1, LAYER1_METRICS)},
        "layer2": {
            "aggregates": diff_aggregates(l2_overall, l2_overall, LAYER2_METRICS),
            "per_entry": diff_per_entry(l2_pe, l2_pe),
            "context": {},
        },
    }
    passed, failures, flags, notes = run_gate(diff)

    if not passed:
        print("BASELINE INVALID: gate fails on baseline-vs-baseline:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)

    print("Baselines valid: both load, all metrics present, gate passes self-comparison.")
    sys.exit(0)


if __name__ == "__main__":
    main()