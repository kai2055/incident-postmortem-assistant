# Finding: Layer 2 Baseline, and a Grounding Filter That Leaked

**Date:** 24 July 2026  
**Measured on:** 15 descriptions through the full agent, on OpenRouter  
**Result:** first measured Layer 2 baseline; one grounding bug found and fixed

---

## Why this matters

Layer 2 had 30 unit tests proving the machinery worked, and one integration run judged by eye. It had no numbers. You cannot build Layer 3—which detects regressions by comparing against a baseline—without a baseline to compare to.

This is that baseline. Building it also caught a real bug that the unit tests had missed.

---

## The metrics

Seven, agreed before running so the targets could not be drawn to fit the result.

| Metric | Meaning |
|---|---|
| top-1 accuracy | Is the top-ranked candidate the right incident? The engineer reads the first line. |
| any-hit rate | Did any candidate cite an expected document? Separates ranking failures from retrieval failures. |
| noise rate | Fraction of candidates citing unexpected documents. Measures padding. |
| decline rate | Do no-match entries correctly return nothing? |
| mean candidates | How many candidates come back per run. |
| grounding violations | Candidates citing IDs never retrieved. Must be zero by construction. |
| restatement rate | Heuristic. How often a "cause" is a reworded symptom. Word-overlap based, approximate. |
| mean iterations | Loop efficiency. |

No targets were set. The first clean run is the baseline; Layer 3 will enforce "do not fall below this," not an invented number.

The one exception is grounding violations, which is not a target but an invariant: it must be zero, because the filter removes ungrounded candidates. A non-zero reading means the filter is broken.

---

## The bug the baseline caught

The first run reported **2 grounding violations**. That number is supposed to be impossible, so the tripwire fired.

Both were in L2-003 (the aws-s3 description). Two candidates cited `gitlab-2017-01-31`—a real incident, but not one retrieved for this run.

### Why it slipped through

The grounding filter kept a candidate if **any** cited ID was real:

```python
cited = {...}                 # every id the model cited
if cited & valid_ids:         # at least one is real?
    grounded.append(d)        # keep the whole thing, evidence unchanged
```

So a candidate citing `aws-s3-2017-02-28, gitlab-2017-01-31` passed—aws-s3 is real, the intersection is non-empty—and carried the fabricated gitlab citation through untouched.

**The filter checked that at least one citation was grounded. It never checked that every citation was.** One real id smuggled in any number of invented ones.

### The fix

Two stages instead of one:

```python
real = cited & valid_ids
if not real:
    continue                          # nothing grounds this, drop it
d["evidence"] = ", ".join(sorted(real))  # keep only the real citations
grounded.append(d)
```

A candidate now survives only if it has a real citation, and its evidence is rewritten to contain only real citations. Fabricated ids are stripped, not tolerated.

Covered by a new test, `test_diagnose_strips_partial_fabrication`, which feeds one real and one fake id and asserts only the real one remains.

### Why the unit tests missed it

The existing grounding test, `test_diagnose_drops_fabricated_ids`, used candidates that were *entirely* fabricated—those were correctly dropped. The gap was the *mixed* case: one real citation plus one fake. No test exercised it, so nothing failed. The scoring run on real model output was the first thing to hit it.

This is the point of scoring against real output: unit tests check the cases you thought of, evaluation catches the ones you didn't.

---

## The baseline (after the fix)

| Metric | Value |
|---|---|
| top-1 accuracy | 0.625  (5 of 8 with a primary cause) |
| any-hit rate | 0.615 |
| noise rate | 0.444 |
| decline rate | 1.000  (2 of 2 no-match entries) |
| mean candidates | 1.80 |
| grounding violations | 0 |
| mean iterations | 2.20 |
| restatement rate (heuristic) | 0.00 |

---

## Reading it

**What works well**

Decline rate is perfect. Both no-match descriptions and both partials whose second clause had no match correctly returned nothing. The reliability behaviour—declining rather than inventing—holds.

Mean candidates fell from 5 (before the anti-padding prompt work) to 1.8. The list no longer pads.

Grounding is clean and now provably so.

**What does not**

Noise rate 0.444 is high, but it is concentrated, not spread:

| Entry | Candidates | Noise | Note |
|---|---|---|---|
| L2-003 | 5 | 5 | all noise—expected aws-s3, cited others |
| L2-007 | 5 | 4 | expected roblox, mostly wrong |

Those two entries produce almost all the noise in the whole suite. Every other entry is clean or nearly so. So the problem is two specific descriptions the agent handles badly, not a diffuse quality issue.

---

## A named failure mode: the plausible attractor

Three entries produced a diagnosis of Postgres transaction-ID (XID) wraparound:

| Entry | Top cause | Correct? |
|---|---|---|
| L2-005 | XID wraparound | yes—sentry-postgres |
| L2-013 | Postgres Transaction ID Wraparound | yes—sentry-postgres |
| L2-007 | PostgreSQL XID wraparound | **no**—expected roblox |

XID wraparound is a real, specific, well-documented Postgres failure. The model reaches for it whenever it sees database-read-only or cascade symptoms—even on L2-007, which is roblox's service-registry cascade and has nothing to do with Postgres.

This is a confident, specific, wrong answer—exactly the failure the project exists to guard against. A vague wrong answer is easy to distrust. "PostgreSQL XID wraparound" sounds authoritative and would send an on-call engineer down the wrong path during an outage.

---

## Two known-cause misses, not diagnosis bugs

L2-010 (crowdstrike) and L2-011 (cloudflare-r2) both declined with zero candidates. That is not the diagnosis stage failing—it is retrieval. Their symptoms score 0.41 and 0.38, above even the Layer 2 threshold of 0.36, so nothing was retrieved and the agent correctly declined on no evidence.

These are threshold casualties already documented in the Layer 2 threshold finding, surfacing again here. No amount of diagnosis-prompt work fixes them; they need the retrieval side addressed.

---

## What this unblocks

Layer 2 now has a committed baseline across seven metrics and a clean grounding invariant. Layer 3 has something to regress against.

It also has two concrete, located problems to work on rather than a general sense that quality is mediocre: the noise concentrated in L2-003 and L2-007, and the XID-wraparound attractor.

---

## What to try next

- **The XID attractor** needs a prompt or evidence change that stops the model reaching for a specific Postgres failure on non-Postgres incidents.
- **L2-003 and L2-007** deserve individual inspection—what did retrieval return, and why did diagnosis pick wrong from it.
- **A candidate cap** ("return at most three") is worth testing now that scoring exists to measure whether it helps or hurts.
- **The retrieval misses** (L2-010, L2-011) point back at the deeper fix: searching the full description alongside the fragments.

---

## Reproduction

```bash
python -m scripts.score_layer2          # ~16 minutes, saves after each entry
python -m scripts.score_layer2 --only L2-003   # inspect one entry
```

Baseline saved to `data/eval/layer2_baseline.json`, per-entry candidate detail included.