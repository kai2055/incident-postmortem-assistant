# ADR-013: Evidence-Based Tuning of RELEVANCE_THRESHOLD

**Date:** 2026-06-29

**Status:** Accepted

**Supersedes:** the placeholder value set in ADR-008 (`RELEVANCE_THRESHOLD = 1.0`).

---

## Context

`retrieve()` filters ChromaDB results by cosine distance: any result whose
distance exceeds `RELEVANCE_THRESHOLD` is dropped as irrelevant. Smaller
distance means more similar; a stricter (lower) threshold rejects more.

ADR-008 set this to a placeholder `1.0` — effectively "keep everything,"
since almost no chunk in the corpus sits beyond distance 1.0 from a
reasonable query. The consequence: the system never declines. Every query,
including ones with no matching incident in the corpus, returns chunks. For
an incident-retrieval assistant used during a live outage, that is the
dangerous failure mode — handing an engineer a confident but irrelevant past
incident sends them chasing the wrong root cause.

The evaluation suite (ADR-011) was built specifically to make this tunable
with evidence rather than intuition. Its five **no-match probes** — queries
describing plausible incidents that do not exist in the corpus — are the
calibration instrument. The baseline run at threshold 1.0 produced a
**decline rate of 0.000**: the system declined none of the five probes. That
0.000 is not a bug; it is the documented "before" state that justifies this
tuning.

This ADR records the decision of what value to set, the evidence behind it,
and — importantly — the findings about *why* a single distance threshold
cannot fully solve no-match rejection in this corpus.

---

## Investigation

Tuning proceeded in three steps: reconnaissance (look at raw distances before
sweeping), a sweep (measure metrics across candidate thresholds), and a
confirming run (verify the full metric set at the chosen value).

### Step 1 — Reconnaissance: the distances overlap

Before sweeping blind, we inspected raw cosine distances by calling `search()`
directly (which returns distances *before* threshold filtering). We measured
the top (closest) distance for all five no-match probes and for five hard
real queries whose correct answer is known.

**No-match probes — closest junk match (top distance):**

| Probe | Top distance | Closest chunk |
|-------|-------------|---------------|
| DDoS 12h outage | **0.215** | cloudflare-2025-11-18:summary |
| SSL cert expiry | 0.289 | github-auth-2026-02-17:summary |
| Malicious base image | 0.318 | cloudflare-thanksgiving-2023-11-23:summary |
| Kubernetes autoscaling | 0.321 | cloudflare-2025-11-18:root_cause |
| Weather in Paris | **0.465** | cloudflare-waf-2019-07-02:timeline |

**Hard real queries — correct answer's distance:**

| Query (expected doc) | Correct-answer distance |
|----------------------|------------------------|
| github-database-2018-10-21 | 0.198 |
| cloudflare-thanksgiving-2023-11-23 | 0.244 |
| sentry-postgres-2015-07-20 | 0.270 (rank 3; 0.256 top was a near-miss) |
| cloudflare-waf-2019-07-02 | 0.273 |
| cloudflare-2025-11-18 | 0.281 |

**Finding 1 — there is no clean separating gap.** The closest no-match junk
(DDoS at 0.215) is *nearer* to the corpus than four of the five hard real
answers (which sit at 0.244–0.281). No single distance threshold can keep all
real answers while rejecting that DDoS probe: a cutoff at 0.25 (to keep the
real answers) lets the 0.215 junk through; a cutoff at 0.20 (to block the
junk) also blocks the 0.198 real answer and everything above it.

**Finding 2 — the cause is by design, and is itself the insight.** The
no-match probes were written (per ADR-011) to be *plausible* infrastructure
incidents phrased in the same vocabulary as the real corpus — "DDoS
overwhelmed our CDN," "SSL expiry caused auth failures." The embedding model
correctly maps that shared vocabulary to nearby chunks. The probes are
semantically close to real incidents precisely *because* they are well-written
decoys. The tell: "weather in Paris," which shares no domain vocabulary, sits
far out at 0.465 — the system rejects the obviously-unrelated query easily and
only struggles on the plausible-but-absent ones. **Distance measures semantic
similarity; a plausible-but-absent incident is semantically similar by
construction. This is a property of the problem, not a flaw in the retriever.**

### Step 2 — Sweep: locating the knee of the curve

We ran the full 31-query suite at seven thresholds from 0.20 to 0.50
(`scripts/sweep_threshold.py`), collecting hit rate, MRR, and decline rate at
each. Sweep range was chosen from Step 1: below 0.20 real answers die; above
0.50 even "weather" passes.

| Threshold | Hit rate@5 | MRR | Decline rate |
|-----------|-----------|-----|--------------|
| 0.20 | 0.261 | 0.261 | 1.000 |
| 0.25 | 0.652 | 0.652 | 0.800 |
| **0.30** | **1.000** | **0.949** | **0.600** |
| 0.35 | 1.000 | 0.949 | 0.200 |
| 0.40 | 1.000 | 0.949 | 0.200 |
| 0.45 | 1.000 | 0.949 | 0.200 |
| 0.50 | 1.000 | 0.949 | 0.000 |

**Finding 3 — 0.30 is the knee.** Reading from the bottom: tightening from
0.50 to 0.35 rejects the "weather" probe (decline 0.0 → 0.2) at zero cost —
hit rate and MRR stay perfect. Tightening further to 0.30 rejects two more
probes (decline 0.2 → 0.6) *still* at zero cost — hit rate remains 1.000, MRR
0.949. One step further, to 0.25, the curve falls off a cliff: hit rate
collapses to 0.652 to buy only one more probe (decline 0.8). At 0.20, hit rate
is 0.261. So 0.30 is the strictest threshold at which hit rate is still
perfect — the last free step before quality breaks. Every rejection up to 0.30
is free; every rejection past it is expensive.

### Step 3 — Confirming run at 0.30 (and a bug it exposed)

A full `evaluate_suite` at threshold 0.30 was run to confirm the complete
metric set, including the two metrics the sweep did not collect: section
accuracy and filter precision/recall. The sweep had only tracked hit rate,
MRR, and decline rate — and that narrow set hid a real bug.

The confirming run revealed **filter precision/recall/exact had collapsed to
0.333** (one of three filter queries passing) — down from 1.000 at the old
1.0 baseline. The retrieval metrics also showed mild run-to-run jitter near
the cutoff boundary. Running the report repeatedly confirmed the filter drop
was *deterministic* (stable at 0.333), which made it a logic bug, not noise.

**Finding 4 — lowering the threshold wrongly gated metadata-filter queries.**
A filter query ("minor severity incidents," "Cloudflare config-errors") is a
*metadata* question — the correct answer is the full set of documents matching
the filter, independent of how semantically close the query phrase is to those
documents. But `retrieve()` applied the distance threshold to *all* queries,
including filtered ones. At threshold 1.0 nothing was cut, so the bug was
invisible. At 0.30, documents that correctly matched the filter but whose chunk
text sat far (in cosine distance) from the short query phrase were dropped —
and since filter queries are scored by exact set match, losing one document
collapsed precision. Distance filtering and metadata filtering are different
retrieval modes; conflating them was the defect.

**Fix:** `retrieve()` now treats `threshold=None` as "no distance cutoff —
return all metadata-matched results, ranked." `score_filter_query` passes
`threshold=None`, so filter queries get the full shelf. Semantic queries
continue to pass the real threshold. This separates the two retrieval modes at
the source (`retrieve()`), so every caller — including the Layer 2 agent —
gets correct behavior, not just the eval. After the fix, filter metrics
returned to 1.000 and were stable across repeated runs.

This episode is itself a finding: the sweep's narrow metric set (3 of the
suite's metrics) hid a regression that the full report caught. Evaluation
tooling must report the *complete* metric set, or a sweep can "confirm" a
value while silently breaking a metric it does not track.

**Confirmed metric set at 0.30 (post-fix, stable across repeated runs):**

| Metric | Baseline (t=1.0) | Tuned (t=0.30) | Change |
|--------|-----------------|----------------|--------|
| Hit rate@5 | 1.000 | 1.000 | — |
| MRR | 0.949 | 0.949 | — |
| Section accuracy | 0.435 | 0.435 | — |
| Decline rate | 0.000 | **0.600** | **+0.600** |
| Filter precision/recall/exact | 1.000 | 1.000 | — (after fix) |

**Finding 5 — the change is a strict improvement (once the filter bug is
fixed).** Moving from the 1.0 placeholder to 0.30 gained 0.600 decline rate
while leaving hit rate, MRR, section accuracy, and filter metrics untouched.
There is no tradeoff at this value.

---

## Decision

**Set `RELEVANCE_THRESHOLD = 0.30`** in `src/embedding.py`, replacing the
ADR-008 placeholder of 1.0.

This is the knee of the curve: the strictest threshold preserving perfect hit
rate, yielding decline rate 0.600 at zero cost to retrieval quality.

**Distance filtering is accepted as a partial, not total, defense against
no-match queries.** Two of the five probes — DDoS (0.215) and SSL-cert
expiry (0.289), the most plausibly-phrased decoys — sit below 0.30 and still
leak. They cannot be rejected by distance without sacrificing real-answer
recall (Findings 1–3). These cases are delegated to the **generation-layer
decline rule** in `generation.py`: when the LLM is handed retrieved chunks
that do not actually match the query, the grounded prompt instructs it to
respond that no matching incident exists. Relevance judgment for the hard,
semantically-close cases belongs to the model reading the chunks, not to a
scalar distance cutoff.

The system therefore declines in two layers:
- **Distance layer (this ADR):** rejects queries beyond 0.30 — catches the
  obvious and moderately-plausible no-matches. Decline rate 0.600.
- **Generation layer (ADR-011 amendment):** the prompt-based decline judges
  the remaining plausible-but-close cases at answer time.

---

## Options considered

**A — Single tradeoff threshold (rejected as sole solution).** Pick one cutoff
accepting some real-answer loss to maximize decline. Rejected because the
sweep shows the tradeoff is unnecessary at 0.30 (zero cost) and ruinous below
it (hit rate cliff). There is no value where forcing higher decline via
distance alone is worth the recall loss.

**B — Generation-layer decline only, loose threshold (rejected as sole
solution).** Leave the threshold loose and let the LLM judge all relevance.
Rejected because distance *does* do real, free work at 0.30 (0.600 decline) —
discarding that and pushing every no-match decision onto the model wastes a
cheap, deterministic first filter.

**C — Layered: distance at the knee + generation for the rest (chosen).**
Distance filtering at 0.30 takes every free rejection it can; the generation
layer handles the two hard plausible-but-absent probes distance cannot reach
without harming recall. Uses each mechanism where it is strong: distance is
cheap and deterministic for clear cases, the LLM is nuanced for close ones.

---

## Consequences

- `RELEVANCE_THRESHOLD = 0.30` is now the production default. The baseline in
  `data/eval/baseline.json` is regenerated at 0.30 and becomes the reference
  point against which Layer 2 (diagnostic agent) and all future changes are
  measured. The prior 1.0 baseline is retained in git history as the "before"
  state.
- `scripts/sweep_threshold.py` and `data/eval/sweep_summary.json` are
  committed as the evidence trail. The sweep can be re-run if the corpus
  changes, since within-corpus distances shift as documents are added.
- The generation-layer decline rule is now load-bearing, not redundant. Its
  behavior on the two leaking probes (DDoS, SSL-cert) should be verified
  directly — a test that runs those probes through full `answer_query()` and
  asserts a decline. This is the next verification step and is noted as open.
- **Metadata-filter retrieval is now distinct from distance filtering.**
  `retrieve(threshold=None)` returns all metadata-matched results without a
  distance cutoff; `score_filter_query` uses this. This was added in response
  to the bug in Finding 4 and applies system-wide, so Layer 2 can request
  uncapped metadata retrieval when it needs a full set rather than a
  semantically-ranked slice.
- **Known caveat — filter queries are capped at `top_k=5`.** `score_filter_query`
  passes `top_k=5`, so a metadata filter matching more than 5 documents would
  under-recall (Chroma returns only the top 5 by distance, and set-match scoring
  marks the rest as missing). Harmless in the current 15-document corpus, where
  no filter matches more than 5 docs. Deferred fix: either pass a large `top_k`
  for filter queries, or make `top_k=None` mean "no cap" symmetrically with
  `threshold=None`. Same family of bug as the distance-on-filter defect above —
  a semantic-search parameter wrongly constraining a metadata query.
- **Corpus-dependence caveat:** 0.30 is calibrated to *this* 15-document
  corpus. Distances are relative to corpus density; adding documents,
  especially in sparsely-covered categories, can shift where real answers and
  near-miss junk fall. The threshold must be re-swept when the corpus changes
  materially. This is recorded so a future reader does not treat 0.30 as a
  universal constant.
- **Layer 2 interaction (open question):** the diagnostic agent retrieves
  iteratively and cross-references across steps. It may tolerate — or require —
  a different threshold than single-shot Layer 1 retrieval. 0.30 is correct for
  Layer 1; whether Layer 2 re-tunes is deferred to that build, and the sweep
  method here is the tool to re-apply.

---

## Findings summary (for case-study reuse)

1. **No clean gap.** Closest no-match junk (0.215) sits nearer than four of
   five hard real answers (0.244–0.281). No single threshold cleanly separates
   real from absent.
2. **The overlap is by design.** Well-written plausible-but-absent probes are
   semantically close to real incidents *because* they share domain
   vocabulary; the embedding model maps that vocabulary correctly. Distance
   cannot distinguish "plausible and present" from "plausible and absent."
   "Weather in Paris" (0.465, no shared vocabulary) is the control that proves
   the mechanism.
3. **0.30 is the knee.** Strictest threshold preserving hit rate 1.000;
   decline 0.600 free, hit-rate cliff immediately below (0.652 at 0.25).
4. **Tuning exposed a hidden bug.** Lowering the threshold revealed that
   distance filtering was wrongly applied to metadata-filter queries, collapsing
   filter precision to 0.333. The fix (`threshold=None` for filter retrieval)
   separated metadata retrieval from distance filtering at the source. The
   sweep's narrow metric set had hidden this; the full report caught it. Lesson:
   evaluation tooling must report the complete metric set, not a subset.
5. **Strict improvement.** 1.0 → 0.30 gained 0.600 decline at zero cost to hit
   rate, MRR, section accuracy, or filter metrics (post-fix).
6. **Layered decline is the honest design.** Distance handles the cases it can
   cleanly reject; the generation layer handles the semantically-close cases a
   scalar cutoff structurally cannot. The system's reliability comes from two
   defenses, not one number.