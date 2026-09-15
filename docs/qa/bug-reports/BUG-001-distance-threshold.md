# BUG-001 — Distance Threshold Applied Where It Does Not Belong

| Field | Value |
|---|---|
| **ID** | BUG-001 |
| **Reported by** | Nikhil Adhikari |
| **Date** | 2026-06-29 |
| **Component** | `retrieve()` — src/embedding.py |
| **Severity** | Major |
| **Priority** | High |
| **Status** | Closed — fixed and verified |
| **Found in** | TC-06 / TC-07, threshold tuning |
| **Related** | TP-001, ADR-013 |

---

## What Happened

RELEVANCE_THRESHOLD was lowered from 1.0 to 0.30. Semantic queries improved. Filter queries collapsed.

Filter precision, recall, and exact-match all dropped from 1.000 to 0.333. One of three queries passing. The same value across three runs. Not noise. A logic bug.

The defect was already there. At 1.0, nothing ever got cut, so the bad path never ran. A config value changed and the latent bug surfaced.

---

## Environment

- ChromaDB, cosine distance
- nomic-embed-text via Ollama
- 15 normalized post-mortems
- RELEVANCE_THRESHOLD = 0.30, top_k = 5

---

## Reproduction

1. Set RELEVANCE_THRESHOLD = 0.30
2. Run the full 31-query suite (evaluate_suite)
3. Check filter metrics in the report
4. Repeat twice

**Expected:** 1.000 across filter precision, recall, exact-match  
**Actual:** 0.333 across all three

---

## Evidence

| Metric | t = 1.0 | t = 0.30 | Delta |
|---|---|---|---|
| Hit rate@5 | 1.000 | 1.000 | — |
| MRR | 0.949 | 0.949 | — |
| Section accuracy | 0.435 | 0.435 | — |
| Decline rate | 0.000 | 0.600 | +0.600 |
| **Filter precision / recall / exact** | **1.000** | **0.333** | **−0.667** |

Regression is isolated. Everything else held.

---

## Root Cause

`retrieve()` applied the cosine-distance threshold to every query—including metadata-filtered ones.

**Before — src/embedding.py @ 4b72877:**

```python
RELEVANCE_THRESHOLD = 1.0  # loose placeholder; Layer 3 evaluation will tune this

def retrieve(
    query: str,
    collection_name: str = CHROMA_COLLECTION,
    top_k: int = 5,
    filter_metadata: dict = None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> List[dict]:
    query_vector = embed_text(query, "search_query:")
    results = search(query_vector, collection_name, top_k, filter_metadata)
    
    # Keep only results close enough to be relevant
    relevant = [r for r in results if r["distance"] <= threshold]  # ← applied unconditionally
    
    return relevant
```

Two things are wrong here. The list comprehension has no condition—every caller gets the distance cutoff, so semantic ranking and metadata set-retrieval share one path. And the docstring states it as a flat rule ("Drop results whose distance is above the threshold"), with no sign that a metadata query might need different treatment. The defect is in the design, not a slip in the code.

A filter query like "minor-severity incidents" is a set question. The right answer is every document matching the filter. It does not matter how semantically close the query phrase sits to the chunk text. The metadata already decided.

At 1.0, nothing was ever discarded, so the wrong logic produced correct output by accident. At 0.30, documents that matched the filter correctly but sat far in cosine distance got silently dropped. Filter scoring is exact set-match—lose one document, lose the query.

**The real defect:** two retrieval modes—semantic ranking and metadata set-retrieval—forced through one code path, with a parameter meant for one mode leaking into the other.

---

## Fix

`retrieve()` now accepts threshold=None. No distance cutoff. Return all metadata-matched results, ranked.

**After — src/embedding.py @ b96eef3:**

```python
def retrieve(
    query: str,
    collection_name: str = CHROMA_COLLECTION,
    top_k: int = 5,
    filter_metadata: dict = None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> List[dict]:
    query_vector = embed_text(query, "search_query:")
    results = search(query_vector, collection_name, top_k, filter_metadata)
    
    # If threshold is None, skip distance filtering
    if threshold is None:
        return results
    
    relevant = [r for r in results if r["distance"] <= threshold]
    return relevant
```

**Call site — src/evaluation.py:**

```python
def score_filter_query(query_entry: dict, top_k: int, threshold: float) -> dict:
    filter_metadata = query_entry.get("filter") or None
    results = retrieve(
        query_entry["query_intent"],
        top_k=top_k,
        filter_metadata=filter_metadata,
        threshold=None,  # No distance cutoff — return all metadata-matched results
    )
```

Semantic queries keep the real threshold. The two modes are now distinguished at the call site.

Fixed at the source—`retrieve()`, not the eval harness. Every downstream caller inherits it, including the Layer 2 diagnostic agent.

**One residue:** `score_filter_query` still accepts a threshold parameter it never uses. The signature is misleading—a future reader could think changing the suite threshold affects filter scoring. Remove it or rename to `_threshold`.

---

## Verification

| Check | Result |
|---|---|
| Filter metrics restored | 1.000 ✓ |
| Hit rate, MRR, section accuracy unchanged | ✓ No regression |
| Decline rate retained | 0.600 ✓ |
| Stable across 3 runs | ✓ |

---

## What Was Missed

`score_filter_query` passes top_k=5. If a metadata filter matches more than 5 documents, the vector store returns only the top 5 by distance. Set-match scoring counts the rest as missing.

Harmless now—no filter in the 15-document corpus exceeds 5. Same defect class: a semantic parameter constraining a metadata query. Must fix before the corpus grows. Tracked separately.

---

## Lessons Learned

**1. Passing tests at a permissive setting are not evidence of correctness.**

The bug existed from the first line of code. RELEVANCE_THRESHOLD = 1.0 meant the faulty branch never discarded anything. The placeholder was even flagged in the source (# loose placeholder; Layer 3 evaluation will tune this). It was known to be temporary. The defect still hid behind it—because knowing a setting is temporary is not the same as testing what happens when it changes.

**2. Partial metric reporting hides regressions.**

The threshold sweep tracked 3 of 5 metrics—hit rate, MRR, decline rate. It "confirmed" 0.30 as optimal while silently breaking a metric it did not watch. The defect was caught only on the confirming run that reported the full set.

Fix: full metrics on every run. Recorded as risk R3 in TP-001. Enforced by exit criteria.

**3. Determinism separates bugs from noise.**

The first thought was jitter. Three identical runs at 0.333 reclassified it as logic. Worth investigating.