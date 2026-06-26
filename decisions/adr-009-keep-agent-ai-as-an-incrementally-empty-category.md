# ADR-009: Keep agent-ai as an Intentionally Empty Category

**Date:** 2026-06-26

**Status:** Accepted

**Context:**
The corpus controlled vocabulary defines eight root-cause categories, including `agent-ai` (incidents caused by autonomous AI agents). During the expansion to 15 documents, we covered seven of the eight. The only real `agent-ai` incident we found with public detail — the PocketOS production-database deletion by a coding agent — was documented only through a founder's social-media thread and third-party coverage, not a first-party engineering post-mortem we could fetch and verify. Building from it would violate the corpus's first-party-only and no-reconstructed-incidents rules. This raised a schema question: drop `agent-ai` from the vocabulary, or keep it empty.

**Decision:**
Keep `agent-ai` in the controlled vocabulary as a documented, intentionally empty category — no incident, with a note in `corpus/README.md` explaining why. Do not delete it, and do not fill it with a non-first-party-sourced document.

**Options considered:**
- A: Delete `agent-ai` from the vocabulary. Keeps every category populated, but discards a forward-looking category that is becoming increasingly relevant, and would require re-adding it later.
- B: Fill it with the PocketOS incident from third-party sources. Achieves full coverage but breaks the first-party-only rule and reintroduces reconstruction risk — the exact integrity failure the corpus rules exist to prevent.
- C: Keep it in the vocabulary, intentionally empty, with a documented reason (chosen).

**Rationale:**
Option C. Agent-caused incidents are a real and growing failure class, so the category is worth keeping ready in the schema. An honest empty category is more defensible than either deleting a relevant category or populating it with a document that fails the sourcing bar. Corpus integrity — every incident traces to a verified first-party source — is the foundation the evaluation framework's trustworthiness depends on; bending it to hit a coverage number would undermine the whole project's premise. Documenting the gap turns "missing" into "deliberate," which is the correct and interview-defensible state.

**Consequences:**
- The corpus covers 7 of 8 categories; `agent-ai` carries zero incidents by design.
- Tests and evaluation must tolerate a category with no documents (no query can have an `agent-ai` ground-truth answer yet).
- The category is ready to populate the moment a first-party-sourced agent incident appears.
- This sets a precedent: sourcing integrity outranks coverage completeness whenever they conflict.