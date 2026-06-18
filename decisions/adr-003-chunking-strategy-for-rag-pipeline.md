# ADR-003: Chunking Strategy for RAG Pipeline

**Date:** 2026-06-18

**Status:** Accepted

**Context:**
Before embedding, documents need to be split into chunks. Each chunk becomes one vector in ChromaDB — the unit the system retrieves when an engineer queries a past incident. The corpus has consistent structure: every post-mortem has the same five sections (Summary, Timeline, Root Cause, Resolution, Prevention).

**Decision:**
Split on section headers (`## Summary`, `## Timeline`, etc.). Sections over 2000 characters split further on paragraph boundaries. Every chunk includes its section header in the text.

**Options considered:**
- A: Fixed-size chunking (256 tokens, 50 token overlap). Simple, but ignores document structure. Root Cause content ends up mixed with Timeline content in the same chunk.
- B: Recursive character splitting. Better than fixed-size but still structure-blind — does not know that `## Root Cause` is a meaningful boundary.
- C: Section-aware chunking (chosen). Each chunk is one section. Clean, focused, matches how engineers actually think about incidents.

**Rationale:**
Option C. The corpus already has consistent section structure — using it makes retrieval sharper. A query like "how was this resolved" should return a Resolution chunk, not a blob that spans multiple sections. It also makes evaluation clean: the correct answer for a test query is a specific `doc_id` + `section` pair, which is unambiguous. Fixed-size chunks make that fuzzy.

**Consequences:**
- Every chunk carries `doc_id`, `section`, `root_cause_category`, `company`, `date`, `severity`, `title` in metadata — enabling filtered search in ChromaDB.
- Evaluation ground truth is precise and auditable.
- `max_chunk_size` is a config parameter, default 2000 characters.
- Corpus documents with inconsistent headers will fail the test suite — enforced by `test_section_is_allowed_value`.

