# ADR-020 — Layer 3 regression-gate policy

**Status:** Accepted (thresholds provisional)
**Date:** 26 July 2026
**Supersedes:** none
**Related:** ADR-016 (Layer 2 design), ADR-017 (Layer 2 threshold), ADR-019 (hosted vs local inference), `finding-vocabulary-not-mechanism.md`

---

> **Note (baseline rebuild):** the Layer 2 reference numbers quoted in this ADR
> (top1 0.625, any-hit 0.615, noise 0.444) predate the frozen-symptoms baseline
> rebuild. Current frozen baseline: top1 0.667 (of 6), any-hit 0.538, noise 0.471,
> decline 1.000, grounding 0. The *classification and reasoning are unchanged*;
> only the reference values moved. Provisional until averaged across N frozen runs.

## Context

Layer 3 is the evaluation agent. It runs in CI on every push, re-runs the
Layer 1 and Layer 2 evals, compares the fresh numbers to the committed
baseline, and decides pass or fail. On fail it blocks the deploy.

It runs with **no human watching**. So "flag a problem" cannot mean "a person
reads the console." It has to mean an **exit code**: exit 0 lets the deploy
proceed, exit non-zero stops the pipeline. Everything below is in service of
one machine-readable pass/fail.

We already ran this gate by hand once. When the corpus grew 15→20 we
re-indexed, re-evaluated, and triaged what moved into three buckets: a stale
test (fixed the test), a real reclassification (accepted it), and a badly
written query (reworded it). **That triage — stale test vs. real regression vs.
bad test — is the gate logic.** Layer 3 automates it.

---

## Decision: three bins, not one rule

We do **not** apply a single rule to every metric. Each metric is sorted by its
character — its baseline value, its sample size, how coarsely it moves, and the
cost of being wrong about it — into one of three bins.

1. **Hard invariant** — must never move. Any drift fails the gate. No tolerance
   band.
2. **Soft threshold** — allowed to wobble within observed noise, blocked past a
   justified drop.
3. **Report-only** — computed and logged every run so a human can watch the
   trend, but never blocks the deploy.

**The restraint is deliberate.** A gate that fires on every healthy change gets
muted, and a muted gate protects nothing the day a real regression arrives. So
most metrics are report-only by design. A metric earns its way *into* a
blocking bin only when it is both good and stable. Bin 3 is a waiting room, not
a graveyard.

---

## Per-metric classification

| Metric | Layer | Baseline | Bin | One-line reason |
|---|---|---|---|---|
| Grounding violations | 2 | 0 | **Hard (definitional)** | 0 is defined as correct; any citation of a non-retrieved incident is a lie, not a quality dip. |
| Hit rate@10 | 1 | 1.000 | **Hard (empirical)** | Perfect now; every downward step is a real retrieval miss with no noise floor to hide in. |
| Decline rate | 2 | 1.000 | **Hard (empirical)** | Perfect now; any drop means the agent started matching cases it should refuse. No tolerable amount. |
| Filter precision / recall / exact | 1 | 1.000 | **Hard (empirical)** | Perfect and deterministic; a drop is a broken filter, not noise. |
| MRR | 1 | 0.918 | **Soft** | Good value with an observed noise band; protect it, allow wobble. See below. |
| Top-1 accuracy (aggregate) | 2 | 0.625 | **Report-only** + per-entry check | 8 discrete points, 0.125/entry; noise and signal are the same size. Gate per-entry, not on the average. |
| Any-hit (aggregate) | 2 | 0.615 | **Report-only** + per-entry check | Same tiny-discrete sample; gate per-entry. Distinct failure from top-1 (see below). |
| Noise rate | 2 | 0.444 | **Report-only** | Baseline is bad, noise is concentrated in 2 of 15 entries, sample is tiny. No stable floor exists yet. |
| Mean candidates | 2 | 1.80 | **Report-only** | Cost/behaviour signal, not correctness. Watch, don't block. |
| Mean iterations | 2 | 2.20 | **Report-only** | Cost/behaviour signal, not correctness. Watch, don't block. |
| Section accuracy | 1 | 0.500 | **Report-only** | Stable and structural, not noisy; moves only on deliberate chunking/corpus/query changes, which are design decisions not regressions. |

---

## Cross-cutting principle 1 — gate by consequence, not by number

The tuning of a gate follows the **cost of being wrong**, and there are two ways
to be wrong:

- **False alarm** — gate fires on a healthy change. Cost: wasted investigation,
  and eventually the gate gets muted. Kills gate *credibility*.
- **Missed failure** — gate passes a real regression. Cost: broken system ships.
  Defeats gate *purpose*.

Both roads end at "protects nothing." So each metric is padded in the direction
of the error it can afford to make:

- **Grounding** is tuned paranoid: never miss, tolerate false alarms. A
  fabricated citation reaching an on-call engineer mid-outage is
  **unrecoverable** — it lies with authority during an emergency.
- **MRR** is tuned loose: tolerate a small miss, avoid false alarms. A small MRR
  slip is **recoverable** (next run, human review catches it), but a distrusted
  gate is not.

Same engineer, opposite tuning, because the cost of being wrong is opposite.

---

## Cross-cutting principle 2 — small discrete metrics get per-entry checks, not thresholds

A soft threshold needs a **noise band** to sit outside of. That only exists for
metrics with enough data to wobble smoothly.

- **MRR has one.** Measured 0.918 → 0.951 → 0.918 across three *legitimate*
  changes — a swing of ~0.033. That observed band is the tool, not any
  derived ratio. Floor is set outside it (see below).
- **Top-1 and any-hit do not.** 8 data points, 0.125 per entry. The smallest
  possible move (one entry flipping) is *also* the size of a real regression.
  Noise and signal are the same magnitude, so no threshold can separate them.

When the aggregate can't separate signal from noise, drop below it. The gate
checks **named entries**, not the average:

- **Top-1 per-entry check** — flags an entry that led with the correct cause and
  now leads with a wrong one. This is a **ranking regression**.
- **Any-hit per-entry check** — flags an entry that used to have the correct
  incident anywhere in its candidate set and now does not. This is a
  **retrieval regression**.

These are different failures at different pipeline stages. Any-hit tests the
retriever ("was the right answer in the pile at all"); the gap between any-hit
and top-1 tests the ranker on top of it ("was it led with"). Watching both
**localises** a Layer 2 drop to retrieval vs. ranking — the same split a human
would do by hand, surfaced automatically.

**These per-entry checks flag for review; they do not hard-block.** Session
history proves a flipped entry is sometimes a *bad test*, not a bad system (the
badly-written hard query that was reworded, not treated as a regression). So a
per-entry flip triggers the human triage — stale test / real regression / bad
test — rather than an automatic red.

---

## Why the small Layer 2 sample, and why the policy adapts to it

Layer 2's sample is small (15 descriptions, 8 scorable for top-1) because each
entry is expensive ground truth: a realistic failure description, an
established true root cause, and a **frozen** decomposition
(`layer2_symptoms.json`) for reproducibility. Roughly 10× the cost of a Layer 1
query, which is one line.

This is the general tension: **the more trustworthy each test case is, the fewer
you can afford.** The small sample is not a flaw the gate must overcome — it is a
property of the measurement, and the gate adapts to it (per-entry checks instead
of aggregate thresholds). As real outage descriptions accumulate, these
aggregates become gate-able and can graduate out of report-only.

---

## MRR floor (provisional)

- Observed noise band from three legitimate runs: **~±0.033**.
- Floor is set **outside** that band, padded for having only three samples:
  block if MRR drops more than roughly **0.04–0.05** below baseline.
- **Explicitly provisional.** Three data points is a weak noise estimate. The
  exact number is padded on purpose in the false-alarm-avoiding direction and
  will be tightened as runs accumulate. The *reasoning* is the decision; the
  number is a current best guess, not a law.

---



## Section accuracy (0.500) — RESOLVED: report-only

Section accuracy is **report-only**, but for a different reason than the other
report-only metrics.

Noise rate is report-only because it is *too unstable to gate* — bad baseline,
concentrated in two outliers, tiny sample. Section accuracy is the opposite: it
is **stable and structural**. It measured exactly 0.500 in both the original
baseline and the frozen rebuild, and the per-query `section_hit` pattern is not
random — it is a fixed property of which query phrasings match which sections
under the current corpus and chunking. Factual "what caused X" queries match the
Summary section; specific symptom-style queries match the expected section. Same
suite against the same store reproduces 0.500.

Because it is structural, the only things that move it are **deliberate** design
changes — re-chunking, changing corpus sections, or rewording queries. Those are
not regressions to block; they are changes a human makes on purpose and would
want to review, not have CI reject. Gating it would fire on intentional work, not
on breakage. And there is no good value to protect: a soft threshold guards a
strong metric from drifting down within noise, but section accuracy is a mediocre
value sitting still, not a good one at risk.

So: **report-only. Logged every run, never blocks.** A future refinement, if it
ever proves useful, is a report-with-alert — flag loudly (not block) if it drops
sharply, e.g. more than ~0.15, since a cliff would signal an unexpected structural
change in chunking or sections. Not built now; it has never moved.

---

## Baseline update policy

The baseline is a **committed file a human updates on purpose**. CI does **not**
overwrite it on green. If every passing run silently became the new baseline, a
slow regression would creep through — each drop small enough to pass, the floor
sinking behind it. When the suite legitimately changes (new hard queries, corpus
growth), a human re-approves the new numbers as the baseline deliberately.

---

## Consequences

- The gate fires rarely and means it — most metrics are report-only, so the day
  it goes red it is trusted.
- Layer 2 regressions are localised to retrieval vs. ranking automatically.
- Grounding can never ship broken; the run stops before any contaminated metric
  is even computed.
- Thresholds are provisional and will tighten as the run history grows. The
  classification and reasoning are the stable part.

---

## Still to build (this ADR is policy, not code)

1. **Runner** — run both evals, produce current numbers (wires existing scripts).
2. **Comparator** — load baseline, load fresh run, diff metric by metric.
3. **Gate** — this policy as code; grounding checked first and short-circuits.
4. **CI wiring** — GitHub Actions on push, OpenRouter provider (CI can't run
   Ollama).