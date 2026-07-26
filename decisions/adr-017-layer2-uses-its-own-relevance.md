# ADR-017: Layer 2 Uses Its Own Relevance Threshold

**Status:** Accepted
**Date:** 25 July 2026
**Relates to:** ADR-013 (Layer 1 threshold 0.30), ADR-016 (Layer 2 agent)

---

## Context

Layer 2 retrieved nothing. Every symptom the diagnostic agent generated came
back empty, the loop ran to its cap, and the diagnosis was blank.

Layer 2 calls the same `retrieve()` as Layer 1, and inherited its default
threshold of 0.30. That value was tuned in ADR-013 against complete,
hand-written questions, which score cosine distances of 0.20–0.27 against the
corpus.

The agent does not send complete questions. Its Decompose node splits an
incident description into short symptom fragments — "main database
disappeared", "nothing can authenticate". A fragment matches less of a
post-mortem chunk than a full description does, so it scores worse: 0.32–0.41
in measurement. The whole is closer to the document than any of its parts.

So 0.30 discarded everything, and the agent was starved of evidence by a
threshold calibrated for a different kind of input.

## Decision

Layer 2 uses its own threshold, `LAYER2_THRESHOLD = 0.36`, passed explicitly by
the Retrieve node. Layer 1 keeps `RELEVANCE_THRESHOLD = 0.30`. ADR-013 is
unaffected; the parameter already existed on `retrieve()`, so this is a
one-argument change per caller.

## Evidence

A paired suite (`data/eval/layer2_suite.json`, 15 descriptions) was run through
Decompose, the generated symptoms frozen
(`data/eval/layer2_symptoms.json`), and each symptom measured against the
retriever. A sweep across candidate thresholds:

| Threshold | Entries with evidence | Junk leaked |
|---|---|---|
| 0.30 | 0/13 | 0/5 |
| 0.34 | 7/13 | 1/5 |
| **0.36** | **9/13** | **1/5** |
| 0.38 | 9/13 | 2/5 |
| 0.40 | 10/13 | 5/5 |

0.36 is the knee: it unblocks 9 of 13 entries while leaking one junk symptom.
0.38 buys no new entries and doubles the leak. 0.40 is a cliff — every no-match
symptom leaks and decline behaviour collapses.

## Why 0.36 is provisional, not calibrated

The distance bands overlap. A junk symptom ("machines shut themselves down",
0.3340) scores better than a real one ("servers dropping everything", 0.3444).
No threshold separates signal from noise, because the separation does not exist
in the data — more samples would describe the overlap, not remove it.

So 0.36 is a round number chosen from where the table turns, on 27 symptom
measurements across 13 descriptions. It is a working setting, not a calibration.
It should be revisited as the suite grows, and it is exactly the kind of value
Layer 3 should watch for drift.

## Alternatives considered

**Raise the global threshold to 0.36.** Rejected. It would degrade Layer 1,
where 0.30 is well calibrated and where loosening drops the decline rate from
0.600 to 0.200.

**A relative cutoff — keep results within X of the best match.** Rejected. It
fails on flat result sets, where every candidate sits within the window. Clever,
sample-fitted, unlikely to generalise.

## Consequences

Positive: Layer 2 functions. Entries with evidence 0/13 → 9/13.

Negative: four entries still get nothing, some symptoms return the wrong
document, and one junk symptom leaks. Layer 2 goes from never working to working
roughly two-thirds of the time. The deeper fix — searching the full description
alongside the fragments, so rich text meets rich chunks — is deferred and
recorded as the real solution rather than this threshold move.

## Open

- Full-description retrieval as the structural fix
- L2-010 and L2-011 fail even at 0.36 (symptoms at 0.41, 0.38) — retrieval
  misses, not threshold misses