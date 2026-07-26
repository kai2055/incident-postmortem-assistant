# ADR-021 — Layer 3 architecture

**Status:** Accepted
**Date:** 27 July 2026
**Related:** ADR-016 (Layer 2 design), ADR-019 (hosted inference for dev, local
for production), ADR-020 (gate policy)

---

## Context

Layer 3 is the evaluation agent. It re-runs the Layer 1 and Layer 2 evals on a
change, compares the results to a committed baseline, and blocks a deploy if the
system regressed. ADR-020 already fixed the *policy* — which metric is a hard
invariant, which is a soft threshold, which is report-only. This ADR records the
*architecture*: how Layer 3 is built and the decisions made building it.

Four decisions below. Each had a real alternative that was rejected for a stated
reason.

---

## Decision 1 — Runner / Comparator / Gate, split by one job each

Layer 3 is three pieces, not one script:

- **Runner** produces the current numbers (re-index if needed, run both evals,
  write `current_layer1.json` and `current_layer2.json`).
- **Comparator** loads baseline and current, diffs them metric by metric, and
  produces per-entry diffs for Layer 2. It computes differences and nothing
  else.
- **Gate** takes the diff and decides pass/fail. It is the *only* piece that
  decides.

**Why the split.** The tempting alternative is one script that runs, compares,
and decides in a single pass. Rejected because it mixes two different kinds of
thing: *measurement* (what are the numbers, what changed) and *judgment* (does
what changed matter). Keeping them apart means each piece is testable on its
own — the Comparator can be checked with hand-made diffs, the Gate with hand-made
comparisons, neither needs the other to run. It also keeps the judgment in one
place: if the policy changes, only the Gate changes. The Comparator never grows
an opinion.

**The boundary is enforced, not just intended.** The Comparator reports
`grounding_violations` as an ordinary metric with a delta. It does *not* know
grounding is a hard invariant — the Gate knows that. Same for every metric: the
Comparator says "this moved by X," the Gate says "that matters / that doesn't."

---

## Decision 2 — Evaluate Layer 2 from frozen symptoms, not live Decompose

The Layer 2 agent starts by decomposing an incident description into symptoms
(the Decompose node), then retrieves and diagnoses from those symptoms. Decompose
is LLM-driven and **non-deterministic** — the same description produces slightly
different symptoms run to run.

**The decision:** Layer 3 evaluates Layer 2 by entering the graph *at Retrieve*
with symptoms already fixed from `layer2_symptoms.json`, skipping Decompose.

**Why.** The first full Runner pass ran live Decompose and the numbers drifted
against the baseline — decline rate dropped 1.000 → 0.500 — for no real
regression. A no-match entry had leaked a false match because that run's
Decompose phrased its symptoms differently. The lesson: a gate whose own
measurement is non-deterministic can never tell a real regression from its own
noise. It would fire on itself.

Freezing symptoms removes the largest and most controllable noise source.
Retrieve, Assess, and Diagnose are still LLM-driven and still wobble a little, so
the eval is *more* reproducible, not perfectly deterministic — but it is now an
honest reference. The project already anticipated this: `layer2_symptoms.json`
exists to freeze Decompose, produced by `freeze_symptoms.py`. Layer 3 uses it.

**Consequence — the baseline had to be rebuilt.** The old Layer 2 baseline was
built via live Decompose, so it was never a valid regression reference; frozen
runs disagreed with it by construction, not by regression. Both baselines were
rebuilt through the frozen-symptoms path so baseline and future runs are measured
the same way. See ADR-020 for the rebuilt reference numbers.

---

## Decision 3 — CI runs deterministic checks; the live eval is a local gate

CI runs on push (path-filtered to `src/`, `corpus/`, `data/eval/`, `tests/`). It
does **not** run the live eval. It runs the mocked test suite and validates the
committed baselines (they load, have the metrics the gate expects, and pass the
gate against themselves).

**Why not run the real eval in CI.** Retrieval embeds every query through
`nomic-embed-text` via Ollama (`src/embedding.py`), and embedding has no hosted
path — unlike generation, which got a provider seam in ADR-019. A cloud CI runner
cannot run Ollama, so it cannot embed, cannot retrieve, and therefore cannot run
either eval. This is not a bug to fix in the workflow; it is a property of a
local, CPU-bound stack (the Intel Arc GPU is unsupported by Ollama, so inference
is local by necessity).

**Alternatives rejected:**
- *Add an embedding provider seam* (mirror ADR-019 for embeddings). The correct
  long-term fix, but hosted embeddings may not be bit-identical to local ones,
  which would move the baseline and reopen the reproducibility question. Too big
  for the CI task; deferred as future work.
- *Self-hosted runner with Ollama.* Overkill for a solo portfolio project.

**What CI is scoped to, stated honestly:** it verifies *code* (the mocked suite
catches code regressions deterministically) and *artifacts* (the committed
baselines are well-formed). The eval itself is a documented **local** gate,
because it needs the local environment. The Runner, Comparator, and Gate all run
locally as the pre-push discipline — which is how they have been used throughout.
This is a scoping decision, not a gap: CI does what a cloud runner can do
deterministically, and no more.

---

## Decision 4 — Verdicts are tri-state; a decline is not a regression

Each Layer 2 entry's `top1_correct` and `any_hit` are three-valued: `True`,
`False`, or `None`. `None` means the entry was unscorable that run — it declined,
or had no primary cause to score.

**The decision:** the Comparator classifies a verdict *transition*, and the Gate
treats the transitions differently:

- `True → False` is `regressed` — was right, now wrong. A real signal.
- `True → None` is `became_unscorable` — the entry now declines. **Not** a
  regression.
- `False → True` is `improved`, `None → …` is `became_scorable`, and so on.

**Why.** The naive version treats `None` as `False`, so an entry that starts
declining looks like a top-1 failure. It isn't — declining honestly is a safety
property of the system, not a ranking bug. Collapsing the three states into two
would make the gate false-alarm every time an entry legitimately declined. The
tri-state is carried faithfully from the loader (never coerced to bool) through
the Comparator's classifier to the Gate's flags.

**And per-entry regressions flag, they don't block.** On a small suite a flipped
entry may be a bad test, not a bad system (this happened — a badly written query
was reworded, not treated as a regression). So a `regressed` entry is flagged for
human triage; only the aggregate hard invariants and the MRR soft threshold block.

---

## Consequences

- Layer 3 is testable piece by piece; each of Runner, Comparator, Gate was
  verified in isolation before wiring.
- The gate owns a single exit code — 0 passes, non-zero blocks. That code is the
  whole interface CI (and a human) reads.
- Grounding is checked first and short-circuits: a run that fabricated a citation
  is contaminated, so no other metric on that run is even computed.
- CI gives a real, green signal on every push without needing Ollama or burning
  LLM tokens.

## Open / provisional

- **Baselines are provisional** — one frozen run each. Reproducible now, but a
  single run bakes in that run's residual (non-Decompose) wobble. Tighten by
  averaging across N frozen runs. Same posture as ADR-020's provisional
  thresholds.
- **The gate is verified on synthetic breaks and the clean case, not yet on a
  live divergent run.** Its tri-state and threshold logic are unit-tested; its
  behaviour on a real regression will first be seen the next time a corpus or
  code change genuinely moves the numbers.
- **Embedding provider seam** — the enabler for running the full eval in CI —
  is deferred (Decision 3).
- **`--baseline` flag** so rebuilding a baseline is one repeatable command using
  the identical measurement path, rather than promoting a current run by hand.