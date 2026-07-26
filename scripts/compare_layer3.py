"""
Layer 3 comparator — diff current run against baseline.

Loads baseline + current for both layers into a common shape, diffs metric
by metric, and produces per-entry diffs for Layer 2. Computes differences
only — the gate decides pass/fail.
"""

import json
from pathlib import Path

# The metrics the gate actually cares about, per layer. Denominators and
# config keys are deliberately excluded — they're context, not diffed.
LAYER1_METRICS = [
    "hit_rate", "mrr", "section_accuracy", "decline_rate",
    "filter_precision", "filter_recall", "filter_exact_match_rate",
]
LAYER2_METRICS = [
    "top1_accuracy", "any_hit_rate", "noise_rate", "decline_rate",
    "mean_candidates", "grounding_violations", "mean_iterations",
]


def load_layer1(path: Path) -> dict:
    """Return Layer 1 aggregate metrics as a flat {metric: value} dict."""
    data = json.load(open(path))
    return data["results"]["overall"]


def load_layer2(path: Path) -> tuple[dict, dict]:
    """Return (aggregate metrics, per-entry verdicts).

    per-entry maps id -> {top1_correct, any_hit}, preserving None
    (a declined/unscorable entry is None, NOT False).
    """
    data = json.load(open(path))
    overall = data["overall"]
    per_entry = {
        e["id"]: {"top1_correct": e["top1_correct"], "any_hit": e["any_hit"]}
        for e in data["per_entry"]
    }
    return overall, per_entry


def diff_aggregates(baseline: dict, current: dict, metrics: list[str]) -> dict:
    """For each named metric: baseline, current, delta. Skips missing keys."""
    out = {}
    for m in metrics:
        if m not in baseline or m not in current:
            continue
        b, c = baseline[m], current[m]
        out[m] = {
            "baseline": b,
            "current": c,
            "delta": round(c - b, 4) if (b is not None and c is not None) else None,
        }
    return out


def classify_verdict_change(before, after) -> str:
    """Classify a tri-state (True/False/None) verdict transition."""
    if before == after:
        return "unchanged"
    if before is True and after is False:
        return "regressed"       # was right, now wrong — the real signal
    if before is False and after is True:
        return "improved"
    if before is not None and after is None:
        return "became_unscorable"   # e.g. entry now declines — NOT a regression
    if before is None and after is not None:
        return "became_scorable"
    return "changed"


def diff_per_entry(baseline_pe: dict, current_pe: dict) -> dict:
    """Per entry, classify top1 and any_hit transitions. Union of ids in case
    an entry appears in one run but not the other."""
    out = {}
    for eid in sorted(set(baseline_pe) | set(current_pe)):
        b = baseline_pe.get(eid, {"top1_correct": None, "any_hit": None})
        c = current_pe.get(eid, {"top1_correct": None, "any_hit": None})
        out[eid] = {
            "top1_change": classify_verdict_change(b["top1_correct"], c["top1_correct"]),
            "any_hit_change": classify_verdict_change(b["any_hit"], c["any_hit"]),
        }
    return out


def compare(baseline_l1: Path, current_l1: Path,
            baseline_l2: Path, current_l2: Path) -> dict:
    """Assemble the full diff. Computes differences only — no pass/fail."""
    b1 = load_layer1(baseline_l1)
    c1 = load_layer1(current_l1)

    b2_overall, b2_pe = load_layer2(baseline_l2)
    c2_overall, c2_pe = load_layer2(current_l2)

    return {
        "layer1": {
            "aggregates": diff_aggregates(b1, c1, LAYER1_METRICS),
        },
        "layer2": {
            "aggregates": diff_aggregates(b2_overall, c2_overall, LAYER2_METRICS),
            "per_entry": diff_per_entry(b2_pe, c2_pe),
            # denominators carried as context so the gate reads deltas correctly
            "context": {
                "baseline_top1_scored_on": b2_overall.get("top1_scored_on"),
                "current_top1_scored_on": c2_overall.get("top1_scored_on"),
                "baseline_decline_scored_on": b2_overall.get("decline_scored_on"),
                "current_decline_scored_on": c2_overall.get("decline_scored_on"),
            },
        },
    }