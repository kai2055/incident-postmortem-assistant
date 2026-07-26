"""
Measure what the frozen Layer 2 symptoms actually retrieve.

Reads the symptoms produced by scripts/freeze_symptoms.py, runs each one
through the real retriever with the threshold switched off, and reports
where the expected document lands.

Embeddings only - no LLM calls, so this runs in seconds and can be re-run
freely while calibrating.

Per symptom, one of four verdicts:
    PASS       expected document found, distance within the threshold
    THRESHOLD  expected document found and ranked, but filtered out
    RANK       expected document exists but sits below the depth we look at
    MISS       expected document not found at all

Usage:
    python -m scripts.measure_layer2
    python -m scripts.measure_layer2 --depth 20
"""

import argparse
import json
from pathlib import Path

from src.agent import LAYER2_THRESHOLD as RELEVANCE_THRESHOLD
from src.embedding import DEFAULT_TOP_K, retrieve

SUITE_PATH = Path("data/eval/layer2_suite.json")
SYMPTOMS_PATH = Path("data/eval/layer2_symptoms.json")


def doc_of(chunk_id: str) -> str:
    """'github-dns-2024-10-11:root_cause:0' -> 'github-dns-2024-10-11'"""
    return chunk_id.split(":")[0]


def classify(results, expected_docs, depth_limit):
    """
    Return (verdict, rank, distance, doc) for the best expected document
    found in results, or a MISS.
    """
    for pos, r in enumerate(results, 1):
        doc = doc_of(r["id"])
        if doc in expected_docs:
            dist = r["distance"]
            if dist > RELEVANCE_THRESHOLD:
                return "THRESHOLD", pos, dist, doc
            if pos > depth_limit:
                return "RANK", pos, dist, doc
            return "PASS", pos, dist, doc
    return "MISS", None, None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--symptoms", type=Path, default=SYMPTOMS_PATH)
    parser.add_argument("--depth", type=int, default=30,
                        help="how deep to search when looking for the target")
    args = parser.parse_args()

    suite = {q["id"]: q for q in json.load(open(args.suite))}
    frozen = json.load(open(args.symptoms))["entries"]

    print(f"threshold : {RELEVANCE_THRESHOLD}")
    print(f"top_k     : {DEFAULT_TOP_K}  (what the agent actually sees)")
    print(f"searching : {args.depth} deep to locate the target\n")

    tally = {"PASS": 0, "THRESHOLD": 0, "RANK": 0, "MISS": 0, "NOTARGET": 0}
    entries_with_evidence = 0
    problem_lines = []

    for entry in frozen:
        q = suite[entry["id"]]
        expected = set(q["expected_docs"])
        print(f"{entry['id']}  [{entry['kind']}]  -> {', '.join(expected) or 'none expected'}")

        any_hit = False

        for symptom in entry["symptoms"]:
            results = retrieve(symptom, top_k=args.depth, threshold=None)
            top_dist = results[0]["distance"] if results else None
            top_doc = doc_of(results[0]["id"]) if results else "-"
            survivors = len(retrieve(symptom))

            if not expected:
                # no-match entries: any survivor is a leak
                verdict = "LEAK" if survivors else "declined"
                tally["NOTARGET"] += 1
                print(f"    {verdict:10} best {top_dist:.4f} ({top_doc})  "
                      f"survivors={survivors}  | {symptom[:55]}")
                continue

            verdict, rank, dist, doc = classify(results, expected, DEFAULT_TOP_K)
            tally[verdict] += 1
            if verdict == "PASS":
                any_hit = True

            if verdict == "MISS":
                print(f"    {verdict:10} target absent in {args.depth}. "
                      f"best was {top_dist:.4f} ({top_doc})  | {symptom[:55]}")
                problem_lines.append((entry["id"], verdict, symptom, None))
            else:
                over = dist - RELEVANCE_THRESHOLD
                mark = f"over by {over:+.4f}" if over > 0 else ""
                print(f"    {verdict:10} rank {rank:<3} dist {dist:.4f} {mark}  "
                      f"| {symptom[:55]}")
                if verdict != "PASS":
                    problem_lines.append((entry["id"], verdict, symptom, dist))

        if expected:
            entries_with_evidence += 1 if any_hit else 0
            if not any_hit:
                print("    >>> no symptom retrieved the target: agent gets nothing")
        print()

    scored = sum(v for k, v in tally.items() if k != "NOTARGET")
    targeted_entries = sum(1 for e in frozen if suite[e["id"]]["expected_docs"])

    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"  symptoms measured        : {scored}")
    print(f"  PASS                     : {tally['PASS']}")
    print(f"  THRESHOLD (found, cut)   : {tally['THRESHOLD']}")
    print(f"  RANK (found, too deep)   : {tally['RANK']}")
    print(f"  MISS (not found at all)  : {tally['MISS']}")
    print()
    print(f"  entries with at least one hit : {entries_with_evidence} of {targeted_entries}")
    print("  (an entry with zero hits means the agent starts with no evidence)")

    if problem_lines:
        print("\nPROBLEM SYMPTOMS")
        for qid, verdict, symptom, dist in problem_lines:
            d = f"{dist:.4f}" if dist else "n/a"
            print(f"  [{qid}] {verdict:10} {d}  {symptom}")


if __name__ == "__main__":
    main()


