# ADR-004: Framework Strategy — Custom Layer 1, LangGraph at Layer 2

**Date:** 2026-06-19

**Status:** Accepted

**Context:**
The pipeline could be built on a framework (LangChain or LlamaIndex) or written directly against Ollama and ChromaDB. Layer 1 is a straightforward pipeline (ingest, chunk, embed, retrieve, generate). Layer 2 is a multi-step diagnostic agent that decomposes a symptom, runs several retrievals, retries, and synthesises a ranked answer — stateful, looping logic. A gap to address: implementation ability. A framework that hides the mechanics works against learning them.

**Decision:**
Build Layer 1 custom — thin, direct calls to Ollama and ChromaDB. Introduce LangGraph only at Layer 2, where multi-step agent orchestration is hard to hand-write. Use RAGAS for evaluation regardless, since it is framework-agnostic.

**Options considered:**
- A: LlamaIndex for everything. Retrieval-first, less code, but its higher-level abstractions hide the chunking, embedding, and retrieval mechanics — the exact things this project exists to learn. Known to feel like "magic" when customising.
- B: LangChain for everything. Strong for agents via LangGraph, but heavy, large dependency surface, and frequent breaking changes. Overkill for a simple Layer 1 pipeline.
- C: Custom Layer 1 + LangGraph at Layer 2 (chosen). Write the pipeline to understand it; adopt a framework only where it earns its place.

**Rationale:**
Option C. Layer 1 is little code — calling Ollama for vectors and ChromaDB for storage and search is small and fully comprehensible. Writing it keeps the mechanics visible and consistent with the hand-written ingestion and chunking already in place. LangGraph is introduced at Layer 2 because stateful retry-and-decompose loops are genuinely painful to hand-roll, and that is precisely the framework's strength. This also reflects the production pattern of pairing a custom or retrieval layer with an orchestration layer, rather than defaulting to one framework for all of it.

**Consequences:**
- Layer 1 has no framework dependency — fewer moving parts, easier to debug, easier to explain.
- LangGraph (and langchain-core) enter the project only at Layer 2.
- Decision is defensible in interviews: a framework was adopted where it adds value, not by default.
- RAGAS handles evaluation independently of the framework choice.
- Trade-off: Layer 1 forgoes some convenience helpers a framework would provide; acceptable given the small surface and the learning goal.