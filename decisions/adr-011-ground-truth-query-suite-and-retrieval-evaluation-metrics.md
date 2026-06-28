# ADR-011: Ground-Truth Query Suite and Retrieval Evaluation Metrics

**Date:** 2026-06-26

**Status:** Accepted

**Context:**
Layer 1 is mechanically complete — ingest, chunk, embed, retrieve, generate all run, tests pass, and the pipeline produces grounded, cited answers. But mechanical correctness is not enough. We need to know whether retrieval actually finds the right incident when an engineer asks a question, and whether it ranks the right answer near the top. Without this, we cannot tune the distance threshold (ADR-008), we cannot claim the system works for real queries, and we cannot measure whether later changes (Layer 2 agent, reranking, model swaps) improve or degrade quality.

The problem: retrieval quality is invisible without labeled test data. A query like "database replication lag caused auth failures" should return the GitHub 2026 auth incident — but does it? It might return Roblox 2021 or Sentry 2015 instead, and the pipeline would still run without error. The only way to catch this is to ask questions where we already know the answer, then check what retrieval returns.

We needed to decide: what questions to write, how to categorize them by difficulty, what metrics to compute, and how to handle the fact that some queries have no right answer at all.

**Decision:**
Build a ground-truth query suite of 31 questions in 5 categories, with expected answers drawn from the 15-document corpus. Compute four retrieval metrics (hit rate@k, MRR, section accuracy, decline rate) plus set precision/recall for filter queries. Run the suite against `retrieve()` to establish a baseline, then use the results to tune `RELEVANCE_THRESHOLD` (ADR-008) with evidence rather than intuition.

The query suite structure:

| Category | Count | What it tests |
|----------|-------|---------------|
| Easy | 5 | Natural questions about well-known incidents. Tests basic document-level retrieval. |
| Medium (symptom) | 12 | Symptom descriptions without company names, dates, or technology keywords. Tests whether embedding-based retrieval matches meaning rather than keywords. |
| Hard (discrimination) | 6 | Queries with one distinguishing detail that separates similar incidents in the same category. Tests whether retrieval discriminates on substance, not surface. |
| No-match | 5 | Queries describing incidents that do not exist in the corpus. Tests whether the system correctly declines rather than forcing a match. |
| Filter | 3 | Metadata-filtered queries (severity, category, company). Tests whether structured filtering returns the exact expected set. |

Key design rules for the suite:
- Easy queries name the company and year — they are natural questions, not keyword bags, but they carry strong identifying signals.
- Medium and hard queries name no company, no date, no technology — only symptoms and observed behavior. This is what makes them realistic: an engineer mid-outage does not know which past incident matches.
- Hard queries include a `distractors` field listing the plausible wrong answers. This is metadata for evaluation, not part of the query text — the query itself contains no answer options.
- No-match queries test the distance cutoff and the prompt-based decline rule together. A correct decline means the threshold caught it, or the model obeyed the prompt, or both.
- Filter queries use a `filter` field with metadata key-value pairs and an `expected_doc_ids` list. They are scored by set precision and set recall, not by rank.

**Hit definition (locked):**
- Primary metric: document-level. A hit is when the expected `doc_id` appears in the top-k results. `expected_section` guides a secondary, stricter metric but does not gate the primary score.
- Secondary metric: section-level. Of document-level hits, what fraction also returned the expected section?

**The metrics:**

| Metric | What it measures | Blind spot |
|--------|------------------|------------|
| Hit rate@k | Fraction of queries where the right document is in the top-k | Does not care about rank within top-k |
| MRR | Mean reciprocal rank of the first correct result | Only looks at the first correct result; ignores multiple correct answers |
| Section accuracy | Fraction of document-level hits where the right section was also returned | Assumes the document was found |
| Decline rate | Fraction of no-match queries where the system correctly returned "I don't have a matching incident" | Depends on both the distance threshold and the model's prompt obedience |
| Set precision / recall (filter only) | Whether the filtered query returned exactly the expected set | Applies only to structured-filter queries, not semantic retrieval |

**Options considered (query difficulty):**
- A: All queries easy, keyword-saturated. Rejected — produces vanity metrics near 100% that prove nothing about real retrieval quality.
- B: All queries hard, no easy tier. Rejected — hard to debug failures when even basic retrieval is untested.
- C: Tiered difficulty with explicit rules (chosen). Easy tests basic function, medium tests semantic matching, hard tests discrimination, no-match tests decline behavior, filter tests metadata. Each tier has a clear purpose.

**Options considered (hit definition):**
- A: Section-level as primary gate. Rejected — a Summary hit for "what caused X" is still a useful retrieval; punishing it as a miss under-scores a working system.
- B: Document-level primary, section-level secondary (chosen). Matches how the system is actually used: the engineer sees the right incident first, then reads the relevant section.

**Options considered (no-match handling):**
- A: Only test the distance threshold, ignore generation. Rejected — the prompt-based decline rule is a real defense and needs measurement too.
- B: Test the full `answer_query()` path, measuring whether the system declines (chosen). Tests both defenses together, which is what the engineer actually experiences.

**Rationale:**
The query suite is the answer key that makes retrieval measurable. Without it, we can say "the pipeline runs" but not "the pipeline works." The tiered difficulty prevents the softball-suite distortion: easy queries establish baseline function, but the real signal comes from medium and hard queries where the system must match meaning without keyword crutches. The no-match category is distinctive — most RAG demos skip it entirely, but it is the metric that proves the system will not hallucinate answers from weakly related chunks during a live outage. Filter queries are a separate scoring track because they test structured metadata retrieval, not semantic similarity.

The metric pairing of hit rate + MRR is standard and defensible: hit rate says "is it in there," MRR says "is it near the top." Section accuracy adds a stricter check without gating the primary score. Decline rate is the reliability number — the one that matters most for trust.

**Consequences:**
- `data/eval/query_suite.json` holds the 31-entry suite. Each entry has `query` (or `query_intent` for filter queries), `difficulty`, `test_purpose`, and either `expected_doc_id`/`expected_section` (retrieval queries) or `filter`/`expected_doc_ids` (filter queries); hard queries also carry `distractors`.
- `src/evaluation.py` loads the suite, runs each query through `retrieve()` (applying the filter for filter queries), and computes the metrics. It reports per-category breakdowns, not just aggregates.
- Filter queries are scored separately by set precision (returned docs that are correct / total returned) and set recall (returned docs that are correct / total expected).
- The baseline run produces numbers that become the reference point for all future changes — Layer 2 agent build, threshold tuning, model swaps are all measured against this baseline.
- A threshold sweep over the query suite is intended to find the cutoff that maximizes decline rate on no-match queries without degrading hit rate on medium and hard queries, replacing the hardcoded `RELEVANCE_THRESHOLD = 1.0` from ADR-008 with an evidence-based value. This sweep is not yet built or run.
- The suite must be updated if the corpus changes — new incidents may require new discrimination queries or may shift existing expected answers if within-category competition changes.


---

**Amendment (2026-06-28):**

After implementing `src/evaluation.py` and its test suite, three points
diverged from or extended the original decision. The body above is left
intact; these corrections describe what was actually built.

1. **No-match decline is scored at the retrieval layer, not the full
   `answer_query()` path.** The original "Options considered (no-match
   handling)" selected testing the full generate path. The implementation
   instead scores decline in `score_decline_query` as
   `declined = (len(retrieve(...)) == 0)` — i.e. whether the distance
   threshold filtered everything out, measured at retrieval. This is the
   correct layer for the upcoming threshold sweep, since the threshold is
   exactly what that path exercises. The generation-path decline rule (the
   prompt-based "I don't have a matching incident" response) remains tested
   separately in `test_generation.py`. Decline is therefore measured at two
   layers by two different tests, not by one combined path.

2. **`data/eval/baseline.json` is committed to version control, not
   gitignored.** This is a deliberate exception to the project convention
   that generated artifacts (e.g. the ChromaDB store) are gitignored. The
   baseline is documented evidence: committing it makes metric changes
   diffable across commits and across threshold-tuning runs, and gives a
   stable reference an interviewer can be pointed at. The file carries
   `run_metadata` (timestamp, top_k, threshold) so it is self-describing.

3. **Metric logic is implemented as pure functions, separated from the
   impure scoring shell.** `hit_at_k`, `reciprocal_rank`, `split_chunk_id`,
   and `to_chroma_where` take plain inputs and return outputs computed only
   from those inputs — no Ollama, no ChromaDB. The scoring functions
   (`score_retrieval_query`, `score_decline_query`, `score_filter_query`)
   are the impure shell that calls `retrieve()`. This pure-core / impure-
   shell split lets the metric math be unit-tested in milliseconds without
   the model, which is a prerequisite for the fast CI test tier (the slow
   ~15-minute integration suite cannot gate every push). Tests for the pure
   functions live alongside the fast suite; `to_chroma_where`'s tests live
   in `test_vectorstore.py` next to the code they cover.