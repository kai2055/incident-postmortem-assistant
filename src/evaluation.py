"""
Retrieval quality evaluation.

Loads the ground-truth query suite, runs each query through retrieve(), and
computes the metrics defined in ADR-011:

- Hit rate@k : fraction of queries whose expected doc is in the top-k results
- MRR        : mean reciprocal rank of the first correct result (MRR@k)
- Section accuracy : fraction of doc-level hits whose section matches
- Decline rate     : fraction of no-match probes correctly declined (empty result)
- Filter precision / recall : set scored, for filter queries


Three scoring modes dispatched by difficulty:
    easy / medium / hard  -> retrieval mode (hit_at_k, reciprocal_rank)
    no-match              -> decline mode (correct == empty result list)
    filter                -> set-match mode (precision / recall)

"""

import json
import statistics
from pathlib import Path
from datetime import datetime, timezone

from src.embedding import retrieve, RELEVANCE_THRESHOLD


QUERIES_PATH = Path("data/eval/query_suite.json")





def hit_at_k(retrieved_ids: list[str], expected_id: str, k: int) -> bool:
    """Return True if expected_id appears in the first k retrieved_ids"""
    return expected_id in retrieved_ids[:k]


def reciprocal_rank(retrieved_ids: list[str], expected_id: str) -> float:
    """
    Return 1/rank of the first occurence of expected_id, else 0.0.

    Rank is 1-indexed. Caller slices to k beforehand for MRR@k
    
    """
    for i, doc_id in enumerate(retrieved_ids, 1):
        if doc_id == expected_id:
            return 1.0 / i
        
    return 0.0



# Helpers

def split_chunk_id(chunk_id: str) -> tuple[str, str | None]:
    """Split 'cloudflare-r2-2025-03-21:summary:0' into (doc_id, section)."""
    parts = chunk_id.split(":")
    doc_id = parts[0]
    section = parts[1] if len(parts) > 1 else None
    return doc_id, section



def result_doc_ids(results: list[dict]) -> list[str]:
    """
    Ordered list of doc_ids from retrieve() results (best first)
    """
    return [split_chunk_id(r["id"])[0] for r in results]





# Scoring

def score_retrieval_query(query_entry: dict, top_k: int, threshold: float) -> dict:
    """
    Score an easy/medium/hard query: doc-level hit, MRR, section accuracy
    
    """

    results = retrieve(query_entry["query"], top_k=top_k, threshold=threshold)
    doc_ids = result_doc_ids(results)
    expected = query_entry["expected_doc_id"]

    hit = hit_at_k(doc_ids, expected, top_k)
    rr = reciprocal_rank(doc_ids[:top_k], expected)

    # Section accuracy: only meaningful when the doc was found.
    section_hit = None
    expected_section = query_entry.get("expected_section")
    if hit and expected_section:
        for r in results[:top_k]:
            d_id, section = split_chunk_id(r["id"])
            if d_id == expected:
                section_hit = section == expected_section
                break

    return {
        "mode": "retrieval",
        "difficulty": query_entry["difficulty"],
        "query": query_entry["query"],
        "expected_doc_id": expected,
        "retrieved_doc_ids": doc_ids,
        "hit": hit,
        "reciprocal_rank": rr,
        "section_hit": section_hit,
    }



def score_decline_query(query_entry: dict, top_k: int, threshold: float) -> dict:
    """
    Score a no-match probe: correct iff retrieve() returns nothing
    """
    results = retrieve(query_entry["query"], top_k=top_k, threshold=threshold)

    declined = len(results) == 0
    return {
        "mode": "decline",
        "difficulty": "no-match",
        "query": query_entry["query"],
        "declined": declined,
        "leaked_doc_ids": result_doc_ids(results),
    }



def score_filter_query(query_entry: dict, top_k: int, threshold: float) -> dict:
    """
    Score a filter with set precision / recall

    Filter queries get the full metadata matched shelf (threshold=None)
    because the question is "which documents match these metadata criteria,"
    not "which chunks are semantically close to this query"
    
    """
    filter_metadata = query_entry.get("filter") or None
    results = retrieve(
        query_entry["query_intent"],
        top_k=top_k,
        filter_metadata=filter_metadata,
        threshold=None, # No distance cutoff - return all metadata-matched results
    )
    returned = set(result_doc_ids(results))
    expected = set(query_entry.get("expected_doc_ids", []))
    correct = returned & expected

    precision = len(correct) / len(returned) if returned else 0.0
    recall = len(correct) / len(expected) if expected else 0.0

    return {
        "mode": "filter",
        "difficulty": "filter",
        "query_intent": query_entry["query_intent"],
        "precision": precision,
        "recall": recall,
        "exact_match": precision == 1.0 and recall == 1.0,
        "returned": sorted(returned),
        "expected": sorted(expected),
        "extra": sorted(returned - expected),
        "missing": sorted(expected - returned),
    }



# Suite runner


def load_queries(path: Path = QUERIES_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)
    


def evaluate_suite(
    queries: list[dict],
    top_k: int = 5,
    threshold: float = RELEVANCE_THRESHOLD,
) -> dict:
    """Run the full suite at a given top_k and threshold; return all metrics"""

    retrieval, decline, filt = [], [], []

    for q in queries:
        diff = q["difficulty"]
        if diff == "filter":
            filt.append(score_filter_query(q, top_k, threshold))
        elif diff == "no-match":
            decline.append(score_decline_query(q, top_k, threshold))
        else:
            retrieval.append(score_retrieval_query(q, top_k, threshold))
    
    overall = {"top_k": top_k, "threshold": threshold, "total_queries": len(queries)}


    if retrieval:
        hits = [r for r in retrieval if r["hit"]]
        overall["hit_rate"] = len(hits) / len(retrieval)
        overall["mrr"] = statistics.mean(r["reciprocal_rank"] for r in retrieval)
        scored_sections = [r for r in hits if r["section_hit"] is not None]
        section_hits = [r for r in scored_sections if r["section_hit"]]
        overall["section_accuracy"] = (
            len(section_hits) / len(scored_sections) if scored_sections else 0.0
        )

    if decline:
        overall["decline_rate"] = sum(r["declined"] for r in decline) / len(decline)


    if filt:
        overall["filter_precision"] = statistics.mean(r["precision"] for r in filt)
        overall["filter_recall"] = statistics.mean(r["recall"] for r in filt)
        overall["filter_exact_match_rate"] = sum(r["exact_match"] for r in filt) / len(filt)

    per_difficulty = {}
    for diff in ("easy", "medium", "hard"):
        rows = [r for r in retrieval if r["difficulty"] == diff]
        if not rows:
            continue
        hits = [r for r in rows if r["hit"]]
        per_difficulty[diff] = {
            "count": len(rows),
            "hit_rate": len(hits) / len(rows),
            "mrr": statistics.mean(r["reciprocal_rank"] for r in rows),
        }

    return {
            "overall": overall,
            "per_difficulty": per_difficulty,
            "retrieval_results": retrieval,
            "decline_results": decline,
            "filter_results": filt,

        }
    


def print_report(results: dict) -> None:
    o = results["overall"]
    line = "=" * 60
    print(line)
    print("RETRIEVAL QUALITY EVALUATION")
    print(line)
    print(f"Total queries : {o['total_queries']}")
    print(f"top_k         : {o['top_k']}")
    print(f"threshold     : {o['threshold']}")
    print()
    print("OVERALL")
    print("-" * 40)
    if "hit_rate" in o:
        print(f"  Hit rate@{o['top_k']:<2}     : {o['hit_rate']:.3f}")
        print(f"  MRR             : {o['mrr']:.3f}")
        print(f"  Section accuracy: {o['section_accuracy']:.3f}")
    if "decline_rate" in o:
        print(f"  Decline rate    : {o['decline_rate']:.3f}")
    if "filter_precision" in o:
        print(f"  Filter precision: {o['filter_precision']:.3f}")
        print(f"  Filter recall   : {o['filter_recall']:.3f}")
        print(f"  Filter exact    : {o['filter_exact_match_rate']:.3f}")
    print()
    print("PER-DIFFICULTY (retrieval)")
    print("-" * 40)
    for diff, m in results["per_difficulty"].items():
        print(f"  [{diff:<6}] n={m['count']:<2}  hit_rate={m['hit_rate']:.3f}  mrr={m['mrr']:.3f}")
    print(line)




def save_results(results: dict, path: Path, top_k: int, threshold: float) -> None:
    """
    Write evaluation results to JSON with run metadata.

    Persists the full results dict (including per-query detail)
    so the baseline is committable and diffable for regression detection.
    Adds timestamp, top_k, and threshold so the file is self-describing

    Args:
        results(): the dict returned by evaluate_suite()
        path: where to write the JSON file
        top_k: the top_k value used for this run
        threshold: the RELEVANCE_THRESHOLD value for this run
    
    
    """

    output = {
        "run_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "top_k": top_k,
            "threshold": threshold,
        },
        "results": results,
    }

    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Results saved to {path}")





def main():
    queries = load_queries()
    top_k = 5
    threshold = RELEVANCE_THRESHOLD
    results = evaluate_suite(queries, top_k=top_k, threshold=threshold)
    print_report(results)

    baseline_path = Path("data/eval/baseline.json")
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    save_results(results, baseline_path, top_k=top_k, threshold=threshold)
    return results



if __name__ == "__main__":
    main()


