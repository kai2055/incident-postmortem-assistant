
"""
Per-query failure diagnosis.

For each query in a suite, retrieves with the threshold switched off and finds
where the expected document actually ranks. Splits failures into two kinds:

  THRESHOLD  - correct document found, but its distance is above the cutoff.
               Fixable by changing the filtering rule.

  RETRIEVAL  - correct document not found at all in the top N.
               Not fixable by any threshold.

Usage:
    python -m scripts.diagnose_queries --suite data/eval/query_suite_plain.json
"""

import argparse
import json
from pathlib import Path

from src.embedding import RELEVANCE_THRESHOLD, retrieve

DEPTH = 15  # how far down the results we look

# Field names that might hold the expected document id
TARGET_KEYS = ["expected_doc", "expected_doc_id", "target", "target_doc",
               "doc_id", "expected", "expected_document"]
TIER_KEYS = ["tier", "difficulty", "category", "type"]


def find_key(entry: dict, candidates: list[str]) -> str | None:
    """Return the first candidate key that exists in the entry."""
    for k in candidates:
        if k in entry:
            return k
    return None


def doc_of(chunk_id: str) -> str:
    """chunk ids look like 'github-dns-2024-10-11:root_cause:0' -> doc part."""
    return chunk_id.split(":")[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=DEPTH)
    args = parser.parse_args()

    queries = json.load(open(args.suite))

    # --- schema detection, printed so it can be checked ---
    sample = queries[0]
    print("Fields found in the suite:", list(sample.keys()))

    target_key = find_key(sample, TARGET_KEYS)
    tier_key = find_key(sample, TIER_KEYS)

    if target_key is None:
        print("\nCould not work out which field holds the expected document.")
        print("Here is the first entry in full:\n")
        print(json.dumps(sample, indent=2))
        print("\nTell me the field name and I'll adjust the script.")
        return

    print(f"Using '{target_key}' as the expected document.")
    print(f"Using '{tier_key}' as the tier." if tier_key else "No tier field found.")
    print(f"Threshold: {RELEVANCE_THRESHOLD}   Looking {args.depth} deep\n")

    threshold_problems = []
    retrieval_problems = []
    passes = []

    for i, q in enumerate(queries, 1):
        expected = q.get(target_key)
        tier = q.get(tier_key, "") if tier_key else ""

        # no-match probes and filter queries have no expected document
        if not expected:
            continue

        results = retrieve(q["query"], top_k=args.depth, threshold=None)

        rank = None
        dist = None
        for pos, r in enumerate(results, 1):
            if doc_of(r["id"]) == expected:
                rank = pos
                dist = r["distance"]
                break

        if rank is None:
            verdict = "RETRIEVAL"
            retrieval_problems.append((i, q["query"], expected, tier))
            print(f"[{i:2}] {verdict:9} not in top {args.depth}  | want: {expected}")
        elif dist > RELEVANCE_THRESHOLD:
            verdict = "THRESHOLD"
            threshold_problems.append((i, q["query"], expected, rank, dist, tier))
            print(f"[{i:2}] {verdict:9} rank {rank}, dist {dist:.4f}  | want: {expected}")
        else:
            verdict = "pass"
            passes.append((i, rank, dist))
            print(f"[{i:2}] {verdict:9} rank {rank}, dist {dist:.4f}")

    total = len(passes) + len(threshold_problems) + len(retrieval_problems)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  scored queries      : {total}")
    print(f"  passing             : {len(passes)}")
    print(f"  threshold problems  : {len(threshold_problems)}  (fixable by rule change)")
    print(f"  retrieval problems  : {len(retrieval_problems)}  (NOT fixable by threshold)")

    if threshold_problems:
        print("\nTHRESHOLD PROBLEMS — correct document found, then discarded")
        for i, query, expected, rank, dist, tier in threshold_problems:
            over = dist - RELEVANCE_THRESHOLD
            print(f"\n  [{i}] {tier}")
            print(f"      query : {query[:90]}")
            print(f"      want  : {expected}")
            print(f"      rank  : {rank}   distance {dist:.4f}   over by {over:.4f}")

    if retrieval_problems:
        print("\nRETRIEVAL PROBLEMS — correct document never surfaced")
        for i, query, expected, tier in retrieval_problems:
            print(f"\n  [{i}] {tier}")
            print(f"      query : {query[:90]}")
            print(f"      want  : {expected}")


if __name__ == "__main__":
    main()