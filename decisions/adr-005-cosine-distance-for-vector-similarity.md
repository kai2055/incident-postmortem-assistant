# ADR-005: Cosine Distance for Vector Similarity

**Date:** 2026-06-19

**Status:** Accepted

**Context:**
ChromaDB measures how close two vectors are using a distance metric. It must be set when the collection is created. ChromaDB defaults to L2 (straight-line distance) if nothing is specified. The first indexing run silently used L2, producing distances in the hundreds — hard to interpret and inconsistent with the intended design.

**Decision:**
Use cosine distance, set explicitly when creating the collection via `metadata={"hnsw:space": "cosine"}`.

**Options considered:**
- A: L2 / Euclidean (the default). Measures straight-line distance and factors in vector magnitude. Distances are unbounded and harder to reason about.
- B: Cosine (chosen). Measures the angle between vectors — direction, not length. Distances fall in a fixed 0–2 range. Standard for text embeddings.

**Rationale:**
Option B. For text, what matters is semantic direction, not vector length, which is what cosine measures — and `nomic-embed-text` is intended to be compared this way. The fixed 0–2 range is far easier to interpret: after switching, the top match for a known query dropped from ~150 to ~0.18. This interpretability matters directly for the evaluation framework, which will set thresholds on these distances to judge retrieval quality; bounded, predictable numbers make those thresholds meaningful.

**Consequences:**
- The collection must be created with the cosine setting; changing the metric later requires recreating the collection.
- Distances are bounded 0–2, ready for threshold-based evaluation in Layer 3.
- The first run's L2 distances are not comparable to later cosine distances — a reminder that "looks right" (correct ranking) can still hide a wrong setting (unintended metric).