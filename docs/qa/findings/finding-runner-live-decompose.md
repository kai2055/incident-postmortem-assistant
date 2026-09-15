# Finding — the Layer 3 runner measures against live Decompose, not frozen symptoms

**Date:** 26 July 2026  
**Surfaced by:** first full end-to-end run of `scripts/run_layer3.py`  
**Related:** ADR-016 (Layer 2 design), ADR-020 (Layer 3 gate policy), `data/eval/layer2_symptoms.json`, `finding-vocabulary-not-mechanism.md`

---

## What happened

The first full run of the Layer 3 runner produced Layer 2 numbers that moved against the committed baseline:

| metric | baseline | this run |
|---|---|---|
| top1_accuracy | 0.625 (of 8) | 0.714 (of 7) |
| any_hit_rate | 0.615 | 0.538 |
| noise_rate | 0.444 | 0.333 |
| decline_rate | 1.000 (of 2) | 0.500 (of 2) |
| mean_candidates | 1.80 | 1.40 |
| grounding_violations | 0 | 0 |
| mean_iterations | 2.20 | 2.20 |

Layer 1 reproduced almost exactly (hit rate 1.000, MRR 0.918 vs 0.9177). Layer 2 did not.

The headline: **decline_rate dropped 1.000 → 0.500**, which under ADR-020 is a hard invariant and would fail the gate. It is 2 no-match entries scored, so 0.5 is literally one entry flipping—one no-match description (L2-015) stopped declining and leaked a candidate ("XID wraparound").

---

## Why it moved—not a regression, a reproducibility gap

The movement is **not** a code or corpus regression. The store was freshly re-indexed and Layer 1 reproduced perfectly, so retrieval is sound. The cause is that **the runner ran the full live graph, including the Decompose node.**

Decompose is LLM-driven and non-deterministic. Its output—the symptom breakdown that everything downstream retrieves against—varies run to run. So each run of the runner as written is measuring against a *different* set of symptoms, and the metrics wobble accordingly. The L2-015 leak is a known pattern: the vocabulary-not-mechanism false positive (the model reaching for an authoritative failure—Postgres XID wraparound—because symptoms rhyme, documented separately). It appears or doesn't depending on how Decompose phrased the symptoms that run.

The project already anticipated exactly this. `data/eval/layer2_symptoms.json` exists specifically to **freeze Decompose output** so measurement is reproducible. The Layer 2 baseline was built against frozen symptoms. The runner was not—it bypasses the freeze and calls the live graph end to end.

**So current and baseline are not measuring the same thing.** The baseline holds Decompose fixed and measures everything after it; the runner lets Decompose vary and measures the whole chain. Comparing them conflates real regressions with Decompose variance.

---

## Why this matters for the gate

The entire point of Layer 3 is telling a real regression from noise. A gate that runs live Decompose can never do that for Layer 2: every run drifts by an unknown amount from Decompose alone, so any metric movement is ambiguous by construction. decline_rate dropping below its hard invariant on this run is the proof—it looks like a gate failure, but it is Decompose variance on a 2-entry denominator, not a broken system.

A gate that fires on its own measurement noise is the false-alarm failure mode ADR-020 warns about. It would get muted. So the runner must remove the noise source it can control.

---

## The fix

**The Layer 3 runner must measure Layer 2 against frozen symptoms, not live Decompose**—the same way the baseline was built. Concretely: run the graph from the frozen `layer2_symptoms.json` starting point (skip or pin Decompose) rather than calling `create_state(description)` and letting Decompose run fresh.

This makes the runner reproducible and makes current-vs-baseline an apples-to-apples comparison. Retrieval, Assess, and Diagnose can still vary (they are also LLM-driven), but removing Decompose variance is the largest and most controllable noise source, and it is the one the project already decided to freeze.

Deferred question: whether the remaining downstream LLM variance (Retrieve / Assess / Diagnose) is small enough to gate on, or whether more of the chain needs pinning for reproducible measurement. To be answered once frozen-Decompose runs are compared across several repeats—that repeat data is also what tightens the provisional thresholds in ADR-020.

---

## Status of today's work

- Refactor (`run_suite` extracted from `main`): verified clean, committed.
- Runner (`scripts/run_layer3.py`): runs end to end, re-indexes first, writes both current-run files, grounding held at 0. **But not yet correct**—it runs live Decompose. Do not commit as a finished gate runner until the frozen-symptoms fix lands.
- The stale-store regression earlier this session (gitignored ChromaDB indexed against the old 15-doc corpus) is what makes the mandatory re-index step load-bearing; the runner already does it.

---

## Next action

Wire the runner's Layer 2 path to start from frozen symptoms, re-run, and confirm the numbers reproduce the baseline within a small band. Then the runner is a trustworthy gate input and can be committed.