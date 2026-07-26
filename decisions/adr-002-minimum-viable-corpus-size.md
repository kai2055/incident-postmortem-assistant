# ADR-002: Minimum Viable Corpus Size for Pipeline Development

**Date:** 2026-06-16

**Status:** Accepted

**Context:**
The full target corpus is 25 documents across 8 failure categories. Building the RAG pipeline requires a corpus to test against — but waiting for all 25 documents before starting pipeline development would delay feedback on chunking quality, embedding behaviour, and retrieval precision. We needed to decide when the corpus is large enough to begin pipeline work.

**Decision:**
4 normalized, committed corpus documents is the minimum threshold to begin RAG pipeline development. Corpus growth continues in parallel with pipeline and evaluation work.

**Options considered:**
- A: Wait for all 25 documents before touching the pipeline. Maximum corpus coverage but delays real retrieval testing by weeks.
- B: Start with 2 documents. Too few — retrieval has nothing meaningful to distinguish between, and evaluation metrics would be trivially easy to game.
- C: Start at 4 documents across at least 2 failure categories (chosen). Enough variety to produce non-trivial retrieval results and catch chunking or embedding issues early.

**Rationale:**
Option C. Four documents spanning multiple failure categories (`human-error`, `configuration-error`, `cascading-failure`) means the retrieval system has to do real work — it cannot just return the only document in the corpus. Issues with chunking strategy, embedding quality, and metadata filtering surface early when the corpus is small and controllable, rather than at document 20 when the cause is harder to isolate. Corpus documents continue to be added incrementally as pipeline layers are built.

**Consequences:**
- Pipeline development begins after corpus document 4 is committed.
- New corpus documents are added in parallel — target remains 25 documents.
- The evaluation agent is designed to run automatically on every new corpus addition, so incremental growth does not require manual re-testing.
- Early retrieval metrics will reflect a small corpus and should be interpreted accordingly.