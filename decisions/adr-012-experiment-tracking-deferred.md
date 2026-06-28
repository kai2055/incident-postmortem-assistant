# ADR-012: Experiment Tracking (MLflow) — Deferred

**Date:** 2026-06-28

**Status:** Deferred (not adopted at this time; revisit at the threshold-tuning / sweep stage)

---

## Context

As the evaluation framework (ADR-011) starts producing metrics across multiple
configurations — different `RELEVANCE_THRESHOLD` values, later different
embedding models or chunking strategies — we will be comparing *runs*: "at
threshold 0.30, decline rate was 0.600; at 0.25 it was 0.800 but hit rate fell
to 0.652." The question is whether to adopt an experiment-tracking tool
(MLflow being the obvious candidate) to record and compare these runs, and if
so, when.

MLflow has three broad components:
1. **Tracking** — log parameters and metrics per run, compare runs in a UI.
2. **Model Registry** — version and stage trained model artifacts.
3. **Serving** — deploy registered models behind an endpoint.

Only the **tracking** component is potentially relevant here. The registry and
serving components do not apply: this system runs inference through local
Ollama models that are pulled, not trained, so there is no trained-model
artifact to version, stage, or serve. There is no model lifecycle for MLflow
to manage — only retrieval-quality experiments to compare.

## Decision

**Do not adopt MLflow now. Revisit at the threshold-tuning / sweep stage**,
and adopt only the tracking component if the simpler approach proves
insufficient.

The reasoning for *not now*:

- **MLflow logs metrics; it does not compute them.** The metric functions
  (`hit_at_k`, `reciprocal_rank`, the scoring modes in `evaluation.py`) are
  required regardless of whether MLflow exists. Adopting it removes zero lines
  of necessary work and adds none of the metric logic. It is purely a
  recording-and-comparison convenience.
- **The payoff is concentrated at the sweep, not the baseline.** A single
  baseline run has nothing to compare against. The value of run-comparison
  only appears once we sweep multiple thresholds. Adopting tracking before
  that point is wiring infrastructure speculatively, before there is anything
  to track.
- **A lighter approach may suffice.** For a sweep of a handful of thresholds,
  a loop over `evaluate_suite`, a printed table, and a committed JSON summary
  (`sweep_summary.json`) provide the same comparison capability MLflow's
  tracking UI would, without the dependency. MLflow's tracking earns its keep
  when there are many runs, many metrics, and a need to compare across sessions
  over time — a scale this project has not reached.

Adopting infrastructure before feeling the need it solves is the
planning-ahead-of-building pattern this project explicitly guards against. The
metric functions are needed now; the tracking tool is not.

## Consequences

- No MLflow dependency is added at this stage. `requirements.txt` is unchanged.
- The threshold sweep (ADR-013) was carried out with the lighter approach:
  `scripts/sweep_threshold.py` loops `evaluate_suite` across candidate
  thresholds, prints a comparison table, and persists `sweep_summary.json` as
  committed evidence. This was sufficient to locate the chosen threshold; the
  lighter approach was *not* found wanting, which retroactively supports the
  deferral.
- If a future need arises — many-run sweeps, cross-session comparison, richer
  metric history than a flat JSON can comfortably hold — adopt MLflow's
  tracking component with a local file backend. The integration is small
  (roughly: wrap each `evaluate_suite` call in `mlflow.start_run()`,
  `log_param("relevance_threshold", t)`, `log_metric(...)` for each metric).
  Because the metric functions already exist and are pure, the integration is a
  thin logging shell around them, not a rewrite.
- The Model Registry and Serving components remain out of scope for as long as
  the system uses pulled (not trained) local models. This would only change if
  the project began training or fine-tuning its own models.

## Status note

As of the threshold-tuning work (ADR-013), the lighter JSON-and-table approach
was sufficient and MLflow was not needed. This ADR remains **Deferred** rather
than **Rejected**: the tracking component is a reasonable future addition if
the evaluation workload grows, and this record exists so that adoption, if it
happens, is a deliberate decision against a documented baseline rather than a
default reach for tooling.