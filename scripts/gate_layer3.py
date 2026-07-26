"""
Layer 3 gate — apply the ADR-020 policy to a comparator diff.

Consumes the dict from compare_layer3.compare() and decides pass/fail.
Grounding is checked first and short-circuits. Each check returns a list
of failure messages (empty = passed); a single top-level caller owns the
exit code so every check stays unit-testable without a process exit.
"""

import sys
from pathlib import Path
from scripts.compare_layer3 import compare

BASELINE_L1 = Path("data/eval/baseline.json")
CURRENT_L1 = Path("data/eval/current_layer1.json")
BASELINE_L2 = Path("data/eval/layer2_baseline.json")
CURRENT_L2 = Path("data/eval/current_layer2.json")

# MRR soft threshold: drops within the observed noise band are tolerated,
# drops past the floor fail. Floor derived from the ~0.033 noise band seen
# across three legitimate runs, padded for a weak 3-sample estimate (ADR-020).
# Provisional — tighten as run history grows.
MRR_MAX_DROP = 0.05


# Hard invariants: (layer, metric). Any drop below baseline fails.
# Grounding is handled separately (it short-circuits), so it's not here.
HARD_INVARIANTS = [
    ("layer1", "hit_rate"),
    ("layer1", "filter_precision"),
    ("layer1", "filter_recall"),
    ("layer1", "filter_exact_match_rate"),
    ("layer2", "decline_rate"),
]


REPORT_ONLY = [
    ("layer1", "section_accuracy"),
    ("layer2", "noise_rate"),
    ("layer2", "mean_candidates"),
    ("layer2", "mean_iterations"),
    ("layer2", "top1_accuracy"),
    ("layer2", "any_hit_rate"),
]


def check_grounding(diff: dict) -> list[str]:
    """Hard invariant, checked FIRST. Grounding violations must be 0,
    absolutely — not 'no worse than baseline'. A contaminated run makes
    every other metric meaningless, so any violation short-circuits."""
    failures = []
    g = diff["layer2"]["aggregates"]["grounding_violations"]["current"]
    if g > 0:
        failures.append(
            f"GATE FAILED (hard invariant): grounding_violations = {g}, "
            f"must be 0. The agent cited incidents it never retrieved; "
            f"other metrics on this run are contaminated and were not evaluated."
        )
    return failures


def run_gate(diff: dict) -> tuple[bool, list[str]]:
    """Apply ADR-020. Returns (passed, messages).

    Grounding short-circuits: if it fails, return immediately without
    running any other check — the rest of the run is contaminated.
    """
    grounding_failures = check_grounding(diff)
    if grounding_failures:
        return False, grounding_failures

    # Other checks appended below as we build them (hard invariants, MRR
    # soft threshold, per-entry). Only reached if grounding passed.
    messages: list[str] = []

    passed = len(messages) == 0
    return passed, messages





def check_hard_invariants(diff: dict) -> list[str]:
    """Hard invariants must not drop below baseline. Any negative delta fails.
    These are perfect/near-perfect metrics where every downward step is a real
    failure with no noise floor (ADR-020)."""
    failures = []
    for layer, metric in HARD_INVARIANTS:
        d = diff[layer]["aggregates"][metric]
        if d["delta"] is not None and d["delta"] < 0:
            failures.append(
                f"GATE FAILED (hard invariant): {layer}.{metric} dropped "
                f"{d['baseline']} -> {d['current']} (delta {d['delta']}). "
                f"Must not decrease."
            )
    return failures




def check_mrr(diff: dict) -> list[str]:
    """MRR soft threshold. A drop within the noise band is fine; a drop past
    MRR_MAX_DROP fails. Padded loose on purpose — a distrusted gate that fires
    on healthy wobble protects nothing, and a small MRR miss is recoverable
    (ADR-020: gate by consequence)."""
    failures = []
    d = diff["layer1"]["aggregates"]["mrr"]
    if d["delta"] is not None and d["delta"] < -MRR_MAX_DROP:
        failures.append(
            f"GATE FAILED (soft threshold): layer1.mrr dropped "
            f"{d['baseline']:.4f} -> {d['current']:.4f} (delta {d['delta']}), "
            f"beyond the allowed {MRR_MAX_DROP} floor. Likely a real retrieval "
            f"regression, not noise."
        )
    return failures


def check_per_entry(diff: dict) -> list[str]:
    """Per-entry flags for Layer 2. Regressed entries are FLAGGED for review,
    not failed — a flipped entry on a tiny sample may be a bad test, not a bad
    system (ADR-020). 'became_unscorable' is NOT flagged: an entry that now
    declines is not a ranking regression, it's just no longer scorable."""
    flags = []
    for eid, changes in diff["layer2"]["per_entry"].items():
        if changes["top1_change"] == "regressed":
            flags.append(f"FLAG (review): {eid} top-1 regressed — a ranking "
                         f"regression, was correct, now wrong.")
        if changes["any_hit_change"] == "regressed":
            flags.append(f"FLAG (review): {eid} any-hit regressed — a retrieval "
                         f"regression, the expected incident left the candidate set.")
    return flags


def report_only(diff: dict) -> list[str]:
    """Metrics that are logged every run but never block (ADR-020)."""
    notes = []
    for layer, metric in REPORT_ONLY:
        d = diff[layer]["aggregates"].get(metric)
        if d is not None:
            notes.append(f"  {layer}.{metric}: {d['baseline']} -> {d['current']} "
                         f"(delta {d['delta']})")
    return notes


def run_gate(diff: dict) -> tuple[bool, list[str], list[str], list[str]]:
    """Apply ADR-020. Returns (passed, failures, flags, notes).

    passed is decided ONLY by failures (grounding, hard invariants, MRR).
    flags (per-entry regressions) and notes (report-only) are informational
    and never change passed.
    """
    grounding_failures = check_grounding(diff)
    if grounding_failures:
        # short-circuit: contaminated run, don't even compute the rest
        return False, grounding_failures, [], []

    failures = []
    failures.extend(check_hard_invariants(diff))
    failures.extend(check_mrr(diff))

    flags = check_per_entry(diff)
    notes = report_only(diff)

    passed = len(failures) == 0
    return passed, failures, flags, notes



def main() -> None:
    diff = compare(BASELINE_L1, CURRENT_L1, BASELINE_L2, CURRENT_L2)
    passed, failures, flags, notes = run_gate(diff)

    print("=" * 60)
    print("LAYER 3 GATE")
    print("=" * 60)

    if notes:
        print("\nReport-only (never blocks):")
        for n in notes:
            print(n)

    if flags:
        print("\nFlagged for review (does not block):")
        for f in flags:
            print(f"  {f}")

    if failures:
        print("\nFAILURES (block deploy):")
        for f in failures:
            print(f"  {f}")

    print("\n" + "=" * 60)
    if passed:
        print("GATE PASSED")
        sys.exit(0)
    else:
        print("GATE FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()