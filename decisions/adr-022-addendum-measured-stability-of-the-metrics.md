# ADR-020 Addendum — Measured stability of the metrics

**Date:** (add current date)
**Status:** Accepted — replaces the "provisional, single run" language in ADR-020
with measured numbers.

---

## Why this addendum

ADR-020 set the gate policy and thresholds from a single run each, explicitly
marked provisional, because there was no measurement of how much the metrics
move run-to-run. This addendum reports that measurement: the evaluation was run
repeatedly and the spread recorded, so the gate's classifications and tolerances
now rest on observed variance instead of guesses.

Method: `scripts/stability.py` runs each layer's evaluation N times, saves each
run, and reports mean / min / max / stdev per metric. Layer 1 was run 10 times;
Layer 2 was run 3 times (each Layer 2 run is ~12–18 minutes on hosted inference,
so 3 runs). Layer 2 runs from frozen symptoms, so the variance measured is the
residual non-determinism of the downstream LLM steps (Assess, Diagnose) after the
Decompose step is frozen.

---

## Layer 1 — fully deterministic

Across 10 runs, **every Layer 1 metric had stdev 0.0000** — identical to the
digit on every run:

| Metric | Value | Stdev (10 runs) |
|---|---|---|
| hit_rate@10 | 1.0000 | 0.0000 |
| MRR | 0.9177 | 0.0000 |
| section_accuracy | 0.5000 | 0.0000 |
| decline_rate | 0.5000 | 0.0000 |
| filter precision / recall / exact | 1.0000 | 0.0000 |

**Finding:** Layer 1 retrieval is deterministic. Same store, same queries, same
embeddings, same threshold produce identical results every run. This is a
*stronger* reliability property than low variance — retrieval is reproducible to
the digit.

**Consequence for the policy:** the hard-invariant classification of hit_rate,
filter metrics, and (in the gate) Layer 1 metrics is now *validated by
measurement*, not assumed. There is literally no noise floor — stdev is zero — so
any downward movement is a real regression, never run variance. ADR-020's phrasing
"perfect metrics where every downward step is a real failure with no noise floor"
is now measured fact for Layer 1.

**Correction to the MRR soft-threshold reasoning:** ADR-020 justified MRR's soft
floor by observing it move 0.918 → 0.951 → 0.918 across earlier sessions. This
measurement shows MRR is deterministic *within a fixed corpus and suite* (stdev
0.0000). So that earlier movement was **not run-to-run noise — it was the corpus
and query suite changing between sessions.** The MRR soft threshold is therefore
absorbing *legitimate-corpus-change wobble*, not random run variance. The soft
threshold still makes sense (corpus growth should not trip the gate), but the
reason is sharper: it tolerates deliberate-change drift, not measurement noise.

---

## Layer 2 — two stable metrics, four noisy ones

Across 3 runs (frozen symptoms):

| Metric | Mean | Range | Stdev |
|---|---|---|---|
| grounding_violations | 0.0000 | [0, 0] | **0.0000** |
| decline_rate | 1.0000 | [1.0, 1.0] | **0.0000** |
| mean_iterations | 2.2000 | [2.2, 2.2] | 0.0000 |
| any_hit_rate | 0.4873 | [0.462, 0.538] | 0.0439 |
| top1_accuracy | 0.5333 | [0.429, 0.600] | **0.0915** |
| noise_rate | 0.4533 | [0.400, 0.560] | **0.0924** |
| mean_candidates | 1.4433 | [1.33, 1.67] | 0.1963 |

**Finding 1 — the two hard invariants are rock-solid.** Across 3 runs / 45 total
diagnoses, `grounding_violations` was **0 every time** and `decline_rate` was
**1.000 every time**, both stdev 0.0000. The single most important safety property
— the agent never citing an incident it did not retrieve — holds perfectly under
repetition. This validates treating grounding as a hard invariant checked first:
there is no variance to accommodate, so any non-zero value is unambiguously broken.

**Finding 2 — the aggregate quality metrics carry large run-to-run variance.**
`top1_accuracy` swung from 0.429 to 0.600 across three runs *with identical frozen
inputs* — a stdev of ~0.09, i.e. roughly 17 percentage points of spread purely
from downstream LLM non-determinism. `noise_rate` (stdev 0.092) and
`mean_candidates` (stdev 0.196) are similarly noisy. Individual entries visibly
flip between runs: e.g. L2-006 diagnosed correctly in one run and declined in the
other two, on identical input.

**Consequence for the policy — this validates the per-entry-check design.**
ADR-020 argued that small discrete metrics get per-entry checks, not aggregate
thresholds. This measurement proves it was necessary, not just tidy: a gate that
thresholded `top1_accuracy` (say, "must stay above 0.60") would false-alarm on
roughly half of all runs *of an unchanged system*, because the metric's own noise
band (~0.09) is larger than any meaningful regression it would try to catch.
Aggregate thresholds on top1/any-hit/noise are therefore not just imprecise —
they are unusable. Per-entry checks (flag a named entry that flipped, for human
triage) are the only workable approach, and the report-only classification of
these aggregates is confirmed.

---

## Note on the committed Layer 2 baseline

The committed Layer 2 baseline recorded `top1_accuracy = 0.667` from a single run.
The 3-run mean is **0.533**, and 0.667 sits *above* the observed max of 0.600 —
so the committed baseline was an optimistic single-run snapshot, not a
representative value. Options: (a) reset the baseline to the 3-run mean for a more
honest reference, or (b) keep it but annotate it as a single-run snapshot. Either
is defensible; the per-entry checks (not the aggregate) are what the gate actually
enforces, so the aggregate baseline value is reference-only, not a gate input.

---

## Summary of what changed

- Layer 1 hard invariants: **validated** (stdev 0.0000, deterministic).
- Layer 2 grounding + decline hard invariants: **validated** (stdev 0.0000).
- Layer 2 aggregate quality metrics: **confirmed report-only** — measured noise
  band (~0.09 on top-1) exceeds any regression a threshold could catch, so
  per-entry checks are necessary, not optional.
- MRR soft threshold: **reasoning corrected** — absorbs corpus-change drift, not
  run variance (MRR is deterministic within a fixed corpus/suite).
- Baseline provisionality: **resolved** — thresholds now rest on measured
  stability, not a single run.

The stability data lives in `data/eval/stability/` (per-layer summaries committed;
raw per-run files gitignored).