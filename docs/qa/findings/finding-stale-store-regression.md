# Finding — stale vector store caused a phantom Layer 2 regression

**Date:** 26 July 2026  
**Surfaced by:** first Layer 2 runs while building the Layer 3 runner  
**Related:** ADR-020 (Layer 3 gate policy), `src/embedding.py`, `scripts/run_layer3.py`

---

## What happened

Mid-session, Layer 2 entries that pass in the committed baseline started failing. Two examples:

- **L2-006**—baseline: 3 candidates, correct top-1 hit on `github-database-2018-10-21`, `any_hit: true`. Current run: **0 candidates, declined**, retrieved nothing.
- **L2-001**—baseline: correct incident in candidate set. Current run: 3 candidates, all wrong (`noise 3`), top pick a credential incident when the expected answer was `cloudflare-waf-2019-07-02`.

On the surface this looked like a regression—the system had gotten worse—and it appeared right after a code refactor, so the refactor was the obvious suspect.

---

## Why it was NOT the obvious cause

The refactor was innocent. It only moved a loop (`run_suite` extracted from `main`); it touched no retrieval or graph code. Isolation confirmed this:

- `ollama list`—`nomic-embed-text` was loaded. Embedder fine.
- `git status` / `git log`—corpus untouched since the baseline commit. No data change.
- A second entry (L2-001) also mis-retrieved, so it was not one bad entry—it was systemic to retrieval.
- Comparing to the committed baseline showed the affected entries **used to pass**. So the baseline was right and *current* had drifted—pointing away from a bad baseline and toward something environmental.

---

## Root cause

The **vector store on disk was stale.** The corpus grew from 15 to 20 documents in an earlier commit, but the ChromaDB index at `data/chromadb` had never been rebuilt after that growth. So retrieval was searching the **old 15-doc index** while the suite and baseline expected the **current 20-doc / 107-chunk** corpus. Wrong incidents came back, or none at all.

The reason `git status` gave no warning: **`data/chromadb` is gitignored**—it is a generated artifact, not tracked. So git reported a clean tree while the actual thing retrieval depends on was silently out of date. **A clean git tree says nothing about the state of the index.**

---

## The fix

Re-index so the store matches the current corpus:

```
python -m src.embedding
```

After re-indexing, L2-001 immediately found the expected incident again (`any_hit` went false → true), and the full suite reproduced documented behavior. Fixed.

---

## Why this is load-bearing for Layer 3

This is exactly the failure the Layer 3 runner's **mandatory re-index step** prevents. A gate that evaluated without re-indexing would compare a fresh baseline against a possibly-stale store and report regressions that are not real—the false-alarm failure mode ADR-020 warns about. The re-index is not hygiene; it is a correctness precondition. `scripts/run_layer3.py` re-indexes as its first step for this reason, now demonstrated rather than assumed.

---

## Lessons

- **Gitignored artifacts have no version signal.** A clean tree can sit on top of a stale generated dependency. Never infer store freshness from git.
- **Diagnose environmental vs. logic failures before concluding.** The symptom (entries failing after a refactor) framed the refactor as guilty; the cause was a stale artifact. Isolation, not assumption, found it.
- **The baseline was the tool that cracked it.** Run current, diff against committed baseline, find the flipped entry, isolate cause—the same procedure Layer 3 automates, run here by hand.