# ADR-015: Candidate Depth and the Decision Not to Retune the Threshold

**Status:** Accepted
**Date:** 23 July 2026
**Supersedes:** Nothing. Extends ADR-013 (relevance threshold tuning).

---

## Context

Layer 2 was blocked on a retrieval probe that returned zero results against a
populated store. The working theory was environmental — that the embedding
model was not loaded — and the "agent declines honestly" framing for Layer 2
depended on that theory being either confirmed or replaced.

It was replaced. The investigation found no defect in any application code, and
instead found two problems that had been invisible because neither produces an
error.

This ADR records what was decided about `top_k` and about
`RELEVANCE_THRESHOLD`, and why one was changed and the other was not.

---

## The problem

Every piece of retrieval code was verified correct: the store path, the cosine
distance setting, the `search_document:` / `search_query:` embedding prefixes,
and the `distance <= threshold` comparison. Full detail in the test plan.

The zero result was the system doing exactly what it was written to do.

What made it a problem was phrasing. The 31-query evaluation suite was written
after reading and normalising all 15 post-mortems, so it reuses the documents'
own vocabulary. Real queries do not. An engineer types "database ran out of
connections"; the document says connection pool exhaustion. Same event,
different words, and the distance moves enough to cross the threshold.

To measure this rather than assume it, a paired suite was built:
`data/eval/query_suite_plain.json`. Identical entries, identical
`expected_doc_id`, identical `difficulty` — only the `query` text rewritten in
plain English. Tiers 4 and 5 (no-match probes and filter queries) were held
constant as a control.

The control worked. Decline rate is identical across both suites at every
threshold, which proves the differences below come from the rewritten queries
and nothing else.

---

## What the measurement showed

Both suites, `top_k=5`:

| Threshold | Hit rate (suite vocabulary) | Hit rate (plain English) |
|---|---|---|
| 0.25 | 0.652 | 0.391 |
| **0.30** | **1.000** | **0.826** |
| 0.35 | 1.000 | 0.913 |
| 0.50 | 1.000 | 0.913 |

Two things stand out.

**Phrasing costs four queries.** At the calibrated threshold, 23 of 23 real
queries pass with suite vocabulary; 19 of 23 pass with plain English.

**The plain-English curve flattens at 0.913 and never moves.** Even at 0.50,
where the filter is doing nothing, two queries still fail. Those failures are
not threshold failures. No cutoff value can fix them.

That split — threshold problems versus retrieval problems — is what
`scripts/diagnose_queries.py` was written to separate.

---

## Decision 1: raise `top_k` from 5 to 10

The per-query diagnostic found a query whose correct document ranked **6th at
distance 0.2888**. That distance passes the 0.30 threshold comfortably. The
system never saw it, because `top_k=5` truncated the candidate list before the
threshold was applied.

This is an ordering error in the pipeline. The threshold is supposed to decide
relevance. A fixed candidate count was overriding it and discarding correct
answers before they were evaluated.

Changed in three places:

- `retrieve()` in `src/embedding.py` — default `top_k` 5 → 10
- `run_sweep()` in `scripts/sweep_threshold.py` — hardcoded `top_k=5` → 10
- Retrieve node in `src/agent.py` — `top_k=3` → default

The agent value is worth noting separately. Layer 2 was retrieving fewer
candidates per symptom than Layer 1 uses for a single query, which is
backwards: the agent does harder work and had less evidence to do it with.

Result on the plain-English suite:

| Threshold | Before (`top_k=5`) | After (`top_k=10`) |
|---|---|---|
| 0.30 | 0.826 | **0.870** |
| 0.35 ceiling | 0.913 | **0.957** |

Decline rate unchanged at every threshold. This is a gain with no cost — no
additional noise was admitted. The suite-vocabulary numbers did not move at
all (still 1.000 / 0.949 / 0.600), because that suite already ranked the
correct document first almost everywhere and had nothing waiting at rank 6.

---

## Decision 2: leave `RELEVANCE_THRESHOLD` at 0.30

Two failures remain at 0.30, both missing by less than 0.01:

| Query | Rank | Distance | Over by |
|---|---|---|---|
| "why was cloudflare throwing 502s in 2019" | 2 | 0.3055 | 0.0055 |
| "our edge protection layer maxed out CPU..." | 4 | 0.3092 | 0.0092 |

Moving the threshold to 0.35 would recover both. It was not done, for three
reasons.

**The bands overlap, so no value separates signal from noise.** From ADR-013's
sweep, the no-match probe "DDoS 12h outage" scored 0.215 — closer than four of
the five hard real queries. There is no clean cut available. Every value is a
tradeoff, and picking the one that happens to clear 23 specific queries is
fitting the sample, not the problem.

**23 queries is not enough to justify a decimal.** One of the two failures
misses by 0.0055. Reworded slightly, it would pass, and a threshold tuned to
catch it would look unnecessary. A number tuned this finely will not survive
corpus growth.

**The direction of error is the one we want.** For an incident assistant, the
two failure modes are not equivalent. Returning nothing costs an engineer time.
Returning a confidently wrong past incident during a live outage sends them
after the wrong root cause. Strict is the correct side to fail on, and 0.35
would drop decline rate from 0.600 to 0.200 — admitting substantially more
noise to recover two borderline queries.

---

## Decision 3: report near-misses instead of returning an empty list

The two remaining failures miss by 0.0055 and 0.0092. Returning `[]` throws
that information away.

When nothing clears the threshold, the retriever should report the closest
candidate and its distance rather than silence — for example, that the nearest
match was `cloudflare-waf-2019-07-02` at 0.3055, below the confidence bar.

This is more useful than any threshold value, because it lets the engineer
judge for themselves, and it degrades gracefully as the corpus grows. Not yet
implemented; recorded here as the agreed direction.

---

## Alternatives considered

**Raise the threshold to 0.35.** Rejected. Recovers two queries at the cost of
tripling admitted noise, and does not address the underlying non-separability.

**Relative cutoff — keep results within X of the best match.** Considered
seriously, then rejected. It has real appeal: the BGP query's best result was
0.1996 and the database query's was 0.3035, yet both ranked correctly, which a
fixed line cannot express. But tested against the actual distances it fails on
flat result sets. The "database ran out of connections" query returns 0.3035
through 0.3528 across fifteen chunks, so a 0.05 window keeps everything. It is
a rule that fits this dataset and would likely break on a larger one.

**Cut at the largest gap between consecutive distances.** Better than the fixed
window, and it handles the BGP case well, but it produced a 10-result set on
the same flat query and missed one target entirely. Same objection: clever,
sample-fitted, unlikely to generalise.

**Do nothing and accept 0.826.** Rejected once the rank-6 finding showed a
structural bug rather than a tuning question.

---

## Consequences

**Positive.** Plain-English hit rate at the calibrated threshold rises from
0.826 to 0.870, and the reachable ceiling from 0.913 to 0.957, with no increase
in noise. Layer 2 now retrieves the same depth as Layer 1. The deferred
`score_filter_query` cap is closed. Two evaluation suites now exist, and the
gap between them is a measured quantity rather than an assumption.

**Negative.** Ten candidates per query instead of five means more work per
retrieval, which matters on CPU-bound local inference. Not measured as
significant, but noted.

**Stale artifacts.** `data/eval/baseline.json` was produced at `top_k=5` and
must be regenerated. When it is, the change in numbers is attributable to the
`top_k` fix and not to any change in retrieval quality — this should be stated
explicitly wherever the new baseline is recorded, or the history will read as
unexplained drift.

---

## Open items

**One query is unreachable at any threshold.** "We deployed a security patch
and every single Windows server crashed simultaneously" does not surface
`crowdstrike-2024-07-19` within ten results. This is a retrieval failure, not a
threshold failure, and needs separate investigation — likely chunking or a
vocabulary gap wider than the embedder bridges.

**The corpus count is wrong in documentation.** The live store holds 83 chunks;
documentation records 82. The store is authoritative.

**Decompose parse accepts non-symptom lines.** Every non-empty line from the
LLM becomes a symptom, including preamble such as "Here are the symptoms:",
which is then issued as a search query. Same failure class already fixed in the
Diagnose node. Needs leading bullet/number stripping and a colon-ending guard.

**Calibration will go stale.** Nothing here proves 0.30 or `top_k=10` remain
correct after the corpus grows. That is not solvable by better tuning — it is
the argument for Layer 3, which re-runs these measurements on every corpus
change and reports when the numbers move.

---

## Reproduction

```bash
# paired suites, identical except query text
python -m scripts.sweep_threshold --suite data/eval/query_suite.json
python -m scripts.sweep_threshold --suite data/eval/query_suite_plain.json

# per-query classification: threshold problem vs retrieval problem
python -m scripts.diagnose_queries --suite data/eval/query_suite_plain.json --depth 10
```

Suite equivalence check — confirms only query text differs:

```bash
python -c "
import json
a = json.load(open('data/eval/query_suite.json'))
b = json.load(open('data/eval/query_suite_plain.json'))
assert len(a) == len(b)
for x, y in zip(a, b):
    for k in x:
        if k != 'query':
            assert x[k] == y[k], f'{k} changed'
print('OK - only query text differs')
"
```