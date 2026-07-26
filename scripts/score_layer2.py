"""
Score the diagnostic agent against the Layer 2 suite.

Runs every description through the full graph and measures the quality of the
diagnosis, not just whether the machinery ran. Produces a baseline that
Layer 3 can later compare against.

This calls the LLM - roughly a minute per description on OpenRouter, so about
15 minutes for the full suite. Results are saved after every entry, so an
interrupt costs one run rather than all of them.

Metrics
-------
top1_accuracy       Is the highest-ranked candidate the right incident?
                    The headline number: an engineer reads the first line.
any_hit_rate        Did ANY candidate cite an expected document?
                    Separates ranking failures from retrieval failures.
noise_rate          Fraction of candidates citing unexpected documents.
                    Measures padding.
decline_rate        Do no-match entries correctly return nothing?
mean_candidates     How many candidates come back per run.
grounding_violations Candidates citing IDs that were never retrieved.
                    MUST be zero - it is zero by construction. Non-zero
                    means the grounding filter is broken.
restatement_rate    HEURISTIC. Fraction of candidates that look like a
                    reworded symptom rather than a cause. Word-overlap based,
                    approximate, will misfire. Directional only.
mean_iterations     Loop efficiency. 3 of 3 means the cap ended every run.

Usage:
    python -m scripts.score_layer2
    python -m scripts.score_layer2 --only L2-006
    python -m scripts.score_layer2 --out data/eval/layer2_baseline.json
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.agent import build_diagnostic_graph, create_state, build_diagnostic_graph_from_symptoms, create_state_with_symptoms

SUITE_PATH = Path("data/eval/layer2_suite.json")
OUT_PATH = Path("data/eval/layer2_baseline.json")

# Word overlap above this fraction flags a candidate as a likely restatement.
RESTATEMENT_OVERLAP = 0.5

# Words too common to carry meaning in this domain.
STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "at", "and", "or", "for",
    "from", "with", "our", "was", "were", "is", "are", "started", "due",
    "by", "that", "this", "it", "its", "as", "into", "out",
}


def words(text: str) -> set[str]:
    """Lowercase content words, stopwords and very short tokens dropped."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def overlap(a: str, b: str) -> float:
    """Jaccard overlap between two strings' content words."""
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def doc_of(chunk_id: str) -> str:
    return chunk_id.split(":")[0]


def cited_ids(evidence: str) -> set[str]:
    """Parse the evidence field the same way the grounding filter does."""
    cleaned = evidence.replace("[", "").replace("]", "")
    return {x.strip() for x in cleaned.split(",") if x.strip()}


def score_entry(q: dict, final: dict) -> dict:
    """Score one completed agent run against its ground truth."""
    expected = set(q["expected_docs"])
    primary = q.get("primary_root_cause")
    diagnosis = final.get("diagnosis", [])
    symptoms = final.get("symptoms", [])

    # Every chunk id the agent actually retrieved
    valid_ids = set()
    for hits in final.get("retrieved", {}).values():
        for h in hits:
            if h.get("id"):
                valid_ids.add(h["id"])

    # --- per-candidate analysis ---
    candidates = []
    for rank, d in enumerate(diagnosis, 1):
        cites = cited_ids(d.get("evidence", ""))
        docs = {doc_of(c) for c in cites}

        ungrounded = bool(cites - valid_ids)
        hits_expected = bool(docs & expected)
        hits_primary = primary in docs if primary else False

        best_overlap = max((overlap(d.get("cause", ""), s) for s in symptoms),
                           default=0.0)

        candidates.append({
            "rank": rank,
            "cause": d.get("cause", ""),
            "confidence": d.get("confidence", ""),
            "docs": sorted(docs),
            "hits_expected": hits_expected,
            "hits_primary": hits_primary,
            "ungrounded": ungrounded,
            "symptom_overlap": round(best_overlap, 2),
            "likely_restatement": best_overlap >= RESTATEMENT_OVERLAP,
        })

    n = len(candidates)

    return {
        "id": q["id"],
        "kind": q["kind"],
        "expected_docs": sorted(expected),
        "primary_root_cause": primary,
        "candidate_count": n,
        "iterations": final.get("iterations", 0),
        "sufficient": final.get("sufficient", False),
        "symptoms": symptoms,
        "top1_correct": candidates[0]["hits_primary"] if (candidates and primary) else None,
        "any_hit": any(c["hits_expected"] for c in candidates) if expected else None,
        "noise_count": sum(1 for c in candidates if not c["hits_expected"]) if expected else n,
        "grounding_violations": sum(1 for c in candidates if c["ungrounded"]),
        "restatements": sum(1 for c in candidates if c["likely_restatement"]),
        "declined": n == 0,
        "candidates": candidates,
    }


def aggregate(results: list[dict]) -> dict:
    """Roll per-entry scores into suite-level metrics."""
    scored_top1 = [r for r in results if r["top1_correct"] is not None]
    scored_hit = [r for r in results if r["any_hit"] is not None]
    no_match = [r for r in results if not r["expected_docs"]]

    total_candidates = sum(r["candidate_count"] for r in results)
    total_noise = sum(r["noise_count"] for r in results)
    total_restate = sum(r["restatements"] for r in results)

    def rate(num, den):
        return round(num / den, 3) if den else None

    return {
        "entries": len(results),
        "top1_accuracy": rate(sum(1 for r in scored_top1 if r["top1_correct"]),
                              len(scored_top1)),
        "top1_scored_on": len(scored_top1),
        "any_hit_rate": rate(sum(1 for r in scored_hit if r["any_hit"]),
                             len(scored_hit)),
        "noise_rate": rate(total_noise, total_candidates),
        "decline_rate": rate(sum(1 for r in no_match if r["declined"]),
                             len(no_match)),
        "decline_scored_on": len(no_match),
        "mean_candidates": round(total_candidates / len(results), 2) if results else 0,
        "grounding_violations": sum(r["grounding_violations"] for r in results),
        "restatement_rate_heuristic": rate(total_restate, total_candidates),
        "mean_iterations": round(
            sum(r["iterations"] for r in results) / len(results), 2) if results else 0,
    }


def save(path: Path, results: dict, suite_path: Path, elapsed: float) -> None:
    ordered = [results[k] for k in sorted(results)]
    output = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "suite": str(suite_path),
            "entries_scored": len(ordered),
            "total_minutes": round(elapsed / 60, 1),
        },
        "overall": aggregate(ordered),
        "per_entry": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)


def print_report(results: list[dict]) -> None:
    o = aggregate(results)
    print("\n" + "=" * 60)
    print("LAYER 2 DIAGNOSIS QUALITY")
    print("=" * 60)
    print(f"  entries scored        : {o['entries']}")
    print()
    print(f"  top-1 accuracy        : {o['top1_accuracy']}   (of {o['top1_scored_on']} with a primary cause)")
    print(f"  any-hit rate          : {o['any_hit_rate']}")
    print(f"  noise rate            : {o['noise_rate']}")
    print(f"  decline rate          : {o['decline_rate']}   (of {o['decline_scored_on']} no-match entries)")
    print(f"  mean candidates       : {o['mean_candidates']}")
    print(f"  grounding violations  : {o['grounding_violations']}   (must be 0)")
    print(f"  mean iterations       : {o['mean_iterations']}")
    print()
    print(f"  restatement rate      : {o['restatement_rate_heuristic']}   HEURISTIC, approximate")

    if o["grounding_violations"]:
        print("\n  *** GROUNDING FILTER IS BROKEN - candidates cite unretrieved ids ***")

    print("\nPER ENTRY")
    for r in results:
        top1 = {True: "hit ", False: "MISS", None: "  - "}[r["top1_correct"]]
        print(f"  {r['id']} [{r['kind']:<12}] top1 {top1}  "
              f"cands {r['candidate_count']}  iters {r['iterations']}  "
              f"noise {r['noise_count']}  restate {r['restatements']}")

def run_suite(suite: list[dict], graph, out_path: Path, suite_path: Path) -> list[dict]:
    """Run every description through the graph, return ordered per-entry results.

    Saves after each entry so an interrupt costs one run, not the whole suite.
    """
    results: dict[str, dict] = {}
    start = time.time()

    print(f"Scoring {len(suite)} descriptions. Roughly a minute each.\n")

    for i, q in enumerate(suite, 1):
        print(f"[{i}/{len(suite)}] {q['id']} ({q['kind']})")
        t0 = time.time()
        final = graph.invoke(create_state(q["description"]))
        elapsed = time.time() - t0

        scored = score_entry(q, final)
        scored["seconds"] = round(elapsed, 1)
        results[q["id"]] = scored

        save(out_path, results, suite_path, time.time() - start)

        top = scored["candidates"][0]["cause"] if scored["candidates"] else "(declined)"
        print(f"    {elapsed:.0f}s  {scored['candidate_count']} candidates  "
              f"iters {scored['iterations']}")
        print(f"    top: {top[:70]}")
        if scored["top1_correct"] is False:
            print(f"    expected: {scored['primary_root_cause']}")
        print()

    return [results[k] for k in sorted(results)]


def run_suite_frozen(frozen: list[dict], suite: dict, graph,
                     out_path: Path, suite_path: Path) -> list[dict]:
    """Run each entry from FROZEN symptoms, skipping live Decompose.

    For reproducible eval: Decompose is the biggest run-to-run noise source,
    so we enter the graph at Retrieve with symptoms already fixed. Scoring
    still needs the suite's ground truth (expected_docs, primary_root_cause),
    so `suite` is passed as an id->entry lookup.
    """
    results: dict[str, dict] = {}
    start = time.time()

    print(f"Scoring {len(frozen)} entries from frozen symptoms.\n")

    for i, entry in enumerate(frozen, 1):
        q = suite[entry["id"]]
        print(f"[{i}/{len(frozen)}] {entry['id']} ({entry['kind']})")
        t0 = time.time()
        state = create_state_with_symptoms(entry["description"], entry["symptoms"])
        final = graph.invoke(state)
        elapsed = time.time() - t0

        scored = score_entry(q, final)
        scored["seconds"] = round(elapsed, 1)
        results[entry["id"]] = scored

        save(out_path, results, suite_path, time.time() - start)

        top = scored["candidates"][0]["cause"] if scored["candidates"] else "(declined)"
        print(f"    {elapsed:.0f}s  {scored['candidate_count']} candidates  "
              f"iters {scored['iterations']}")
        print(f"    top: {top[:70]}")
        if scored["top1_correct"] is False:
            print(f"    expected: {scored['primary_root_cause']}")
        print()

    return [results[k] for k in sorted(results)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--only", type=str, default=None)
    args = parser.parse_args()

    suite = json.load(open(args.suite))
    if args.only:
        suite = [q for q in suite if q["id"] == args.only]

    graph = build_diagnostic_graph()
    start = time.time()

    ordered = run_suite(suite, graph, args.out, args.suite)

    print_report(ordered)
    print(f"\nSaved to {args.out}")
    print(f"Total: {(time.time() - start) / 60:.1f} minutes")



if __name__ == "__main__":
    main()
    