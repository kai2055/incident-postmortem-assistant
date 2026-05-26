# ADR-001: Normalized Corpus Schema

**Date:** 2026-05-26

**Status:** Accepted

**Context:**
Our system pulls incident post-mortems from different companies — Cloudflare does long blog posts, GitHub does monthly summaries, GitLab uses issue threads. The formats are completely different. We need to feed these into a RAG pipeline and a diagnostic agent. If the documents are all over the place, retrieval quality drops and evaluation becomes unreliable. So we had to decide: keep the original formats or normalize everything.

**Decision:**
All 25 incident reports will be converted into a single structure. One Markdown file per incident. YAML frontmatter for metadata, then five fixed sections: Summary, Timeline, Root Cause, Resolution, Prevention. We'll use consistent labels for severity and failure category.

**Options considered:**
- A: Leave every document in its original format. Less work now, but the downstream code has to handle five different shapes. Retrieval and eval would suffer.
- B: Normalize to a common schema (the one we chose). Extra manual effort per document, but retrieval becomes fair, and the evaluation metrics actually mean something.
- C: Pure JSON schema. Easy for machines, painful for humans to read and edit. Also less natural for LLMs since they see more Markdown during training.

**Rationale:**
Option B. We only have 25 documents, so the manual work is manageable — maybe 15-20 minutes each. The benefit is that every layer above the corpus (chunking, embedding, retrieval, agent, eval) works with one predictable structure. The frontmatter fields (`severity`, `root_cause_category`) let us slice evaluation results later — like checking if the system retrieves the correct failure type, not just the correct document. Without normalization, our evaluation numbers would be noisy and we wouldn't know why.

**Consequences:**
- We added a 5-point completeness score to filter out weak documents before normalization.
- The ingestion script will assume this exact schema, so adding a new company just means mapping to the same fields — no code changes.
- The hold-out evaluation also depends on this. The test queries we write rely on the Summary and Root Cause sections being structured and comparable.