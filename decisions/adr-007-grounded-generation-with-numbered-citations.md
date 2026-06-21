# ADR-007: Grounded Generation with Numbered Citations

**Date:** 2026-06-21

**Status:** Accepted

**Context:**
The generation step turns retrieved chunks into a written answer. For a tool used during a live outage, two things matter most: the answer must come only from the retrieved post-mortems (not the model's training, which could invent a plausible-sounding root cause), and the engineer must be able to trace each claim back to a real incident. We needed to decide how to enforce that grounding and how to present citations.

**Decision:**
- Prompt the model to use only the provided sources, to return a fixed phrase ("I don't have a matching incident in the sources") when the sources don't answer, and to cite claims with bracketed numbers.
- Use numbered inline citations (`[1]`) written by the model, backed by a deterministic source list (company + date + section) built from retrieval metadata, not from the model.
- Generate with `qwen3:8b` via Ollama; orchestrate the full flow (retrieve then generate) in `answer_query`.

**Options considered (citations):**
- A: Full label inline, e.g. `[Cloudflare, 2025-03-21, Root Cause]`. Self-contained for the reader, but the model types the whole label itself, so it can mistype the date or section — more room to mis-attribute.
- B: Numbered inline plus a deterministic source list (chosen). The model only has to pick the right number; the authoritative label text comes from retrieval metadata.
- C: Let the model produce the source list too. Rejected — the model could fabricate or misstate sources, and we already know exactly what retrieval returned.

**Options considered (no-answer behavior):**
- Strict (chosen): answer fully, or return the fixed decline phrase. Simple and measurable.
- Partial-aware: answer what's supported and flag what isn't. More useful but more complex and harder to evaluate; deferred until evaluation shows whether strict is too conservative.

**Rationale:**
Numbered citations shrink the model's citation job to the one thing it is least likely to get wrong — choosing a number — while the deterministic source list guarantees the labels are correct and can never be fabricated. The fixed decline phrase is a consistent string the evaluation framework can detect, which makes "correctly declined" a measurable outcome. Grounding-first prompting is the foundation the faithfulness metric will later score.

**Consequences:**
- `generation.py` holds `_build_sources` (deterministic numbering), `_build_prompt`, `generate_answer`, and `answer_query`. It calls Ollama and imports `retrieve` from `embedding.py` — a one-way dependency, no cycle.
- The source list is trustworthy regardless of how the model behaves; inline citations are best-effort and get validated by evaluation.
- The prompt alone does not guarantee every claim is cited — citation coverage gaps are real and will be measured by the faithfulness evaluation, not assumed away.
- Strict no-answer behavior may prove too conservative; revisit with partial-aware prompting once evaluation provides numbers.
- In practice `qwen3:8b` emitted no thinking tokens, so no stripping is needed; revisit if other queries produce them.