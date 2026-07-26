"""
Threshold sweep for Layer 2.

Layer 2 inherits RELEVANCE_THRESHOLD = 0.30 from Layer 1, which was tuned on
complete questions scoring 0.20-0.27. Symptom fragments score 0.32-0.41, so
everything is discarded and the agent starts with no evidence.

This sweeps candidate thresholds against the frozen symptoms and reports the
tradeoff at each: how much evidence the agent gets, versus how much noise
gets through.

Embeddings only - no LLM calls, runs in seconds.

Usage:
    python -m scripts.sweep_layer2
"""

import argparse
import json
from pathlib import Path

from src.embedding import DEFAULT_TOP_K, retrieve

SUITE_PATH = Path("data/eval/layer2_suite.json")
SYMPTOMS_PATH = Path("data/eval/layer2_symptoms.json")
OUT_PATH = Path("data/eval/layer2_sweep.json")

THRESHOLDS = [0.30, 0.32, 0.34, 0.35, 0.36, 0.38, 0.40, 0.45, 0.50]


def doc_of(chunk_id: str) -> str:
    return chunk_id.split(":")[0]


def measure(threshold, suite, frozen):
    """Return metrics for one threshold value."""
    entries_with_evidence = 0
    targeted_entries = 0
    symptoms_hit = 0
    symptoms_scored = 0

    junk_symptoms = 0
    junk_leaked = 0

    wrong_doc_returned = 0   # survivors came back, none were the target

    for entry in frozen:
        q = suite[entry["id"]]
        expected = set(q["expected_docs"])

        if not expected:
            # no-match entry: any survivor at all is a leak
            for symptom in entry["symptoms"]:
                junk_symptoms += 1
                if retrieve(symptom, threshold=threshold):
                    junk_leaked += 1
            continue

        targeted_entries += 1
        entry_hit = False

        for symptom in entry["symptoms"]:
            symptoms_scored += 1
            survivors = retrieve(symptom, threshold=threshold)
            docs = {doc_of(r["id"]) for r in survivors}

            if docs & expected:
                symptoms_hit += 1
                entry_hit = True
            elif survivors:
                wrong_doc_returned += 1

        if entry_hit:
            entries_with_evidence += 1

    return {
        "threshold": threshold,
        "entries_with_evidence": entries_with_evidence,
        "entries_total": targeted_entries,
        "entry_rate": round(entries_with_evidence / targeted_entries, 3),
        "symptoms_hit": symptoms_hit,
        "symptoms_total": symptoms_scored,
        "symptom_rate": round(symptoms_hit / symptoms_scored, 3),
        "wrong_doc_returned": wrong_doc_returned,
        "junk_leaked": junk_leaked,
        "junk_total": junk_symptoms,
        "leak_rate": round(junk_leaked / junk_symptoms, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--symptoms", type=Path, default=SYMPTOMS_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    with open(args.suite) as f:
        suite = {q["id"]: q for q in json.load(f)}
    with open(args.symptoms) as f:
        frozen = json.load(f)["entries"]

    print(f"top_k: {DEFAULT_TOP_K}   thresholds: {len(THRESHOLDS)}\n")

    rows = [measure(t, suite, frozen) for t in THRESHOLDS]

    header = (f"{'thresh':>7} | {'entries fed':>12} | {'symptoms hit':>13} | "
              f"{'wrong doc':>10} | {'junk leaked':>12}")
    print(header)
    print("-" * len(header))

    for r in rows:
        print(f"{r['threshold']:>7.2f} | "
              f"{r['entries_with_evidence']:>3}/{r['entries_total']} ({r['entry_rate']:.2f}) | "
              f"{r['symptoms_hit']:>4}/{r['symptoms_total']} ({r['symptom_rate']:.2f}) | "
              f"{r['wrong_doc_returned']:>10} | "
              f"{r['junk_leaked']:>3}/{r['junk_total']} ({r['leak_rate']:.2f})")

    print("\nColumns:")
    print("  entries fed  - descriptions where at least one symptom found its target.")
    print("                 An entry at zero means the agent starts with nothing.")
    print("  symptoms hit - individual symptoms that retrieved their target.")
    print("  wrong doc    - symptoms that returned results, none of them the target.")
    print("                 These are worse than silence: the agent reasons on noise.")
    print("  junk leaked  - symptoms from the no-match entries that returned anything.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({
            "suite": str(args.suite),
            "symptoms": str(args.symptoms),
            "top_k": DEFAULT_TOP_K,
            "results": rows,
        }, f, indent=2)
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()


    