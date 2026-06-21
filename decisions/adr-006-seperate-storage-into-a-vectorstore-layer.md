# ADR-006: Separate Storage into a Vectorstore Layer

**Date:** 2026-06-21

**Status:** Accepted

**Context:**
When retrieval was added, the embedding module held two different jobs: calling Ollama to turn text into vectors, and calling ChromaDB to store and search those vectors. Retrieval also needs ChromaDB. Keeping both in one file mixes two unrelated external dependencies and makes the code harder to read, test, and change.

**Decision:**
Split into two layers by which external system they talk to. `embedding.py` talks only to Ollama. `vectorstore.py` talks only to ChromaDB. The orchestrators that need both — `index_chunks` and `retrieve` — live in `embedding.py` and call into `vectorstore.py`. Dependencies flow one direction: `embedding.py` imports `vectorstore.py`, never the reverse. The search function takes a pre-computed vector, not a query string, so `vectorstore.py` never needs to know Ollama exists.

**Options considered:**
- A: Keep everything in `embedding.py`. Simple, but mixes Ollama and ChromaDB concerns, and one file keeps growing as indexing and retrieval pile in.
- B: Split embedding (Ollama) from vectorstore (ChromaDB), orchestrators on top (chosen).
- C: Put the orchestrators in `vectorstore.py` and let it import `embed_text`. Rejected — `embedding.py` already imports `vectorstore.py` for storage, so this creates a circular import, and it breaks the clean "no Ollama in vectorstore" boundary.

**Rationale:**
Option B. Each module ends up with one external dependency and one job, which is easier to reason about and test. The one-way dependency avoids circular imports (the concrete bug option C would have caused). Making `search` take a vector instead of a string is what keeps `vectorstore.py` pure — query embedding happens one level up, in the `retrieve` orchestrator. The boundary also makes it obvious where new code belongs.

**Consequences:**
- `embedding.py` holds `embed_text`, `embed_chunks`, `index_chunks`, `retrieve`. `vectorstore.py` holds `get_chroma_client`, `store_chunks`, `search`.
- Swapping the vector store later (e.g., pgvector) touches only `vectorstore.py`; swapping the embedding model touches only `embedding.py`.
- Tests split to mirror the modules (`test_embedding.py`, `test_vectorstore.py`), with shared fixtures centralized in `conftest.py`.
- `retrieve` is the read-side mirror of `index_chunks`: both coordinate Ollama then ChromaDB, in the same one-way direction.