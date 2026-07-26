
# ADR-008: Distance-Based Relevance Threshold for Retrieval

**Date:** 2026-06-22

**Status:** Accepted

**Context:**
Before this change, the only thing stopping the system from answering with irrelevant incidents was the prompt instruction telling the model to decline when the sources don't fit. That defense is soft: it depends entirely on the LLM behaving, and a model handed several chunks will often try to construct an answer even when those chunks are unrelated to the question. For a tool used during a live outage, surfacing the wrong past incident is a real harm — it can send an engineer chasing a root cause that never applied. We needed a defense that does not depend on the model's judgment.

Every retrieval result already carries a cosine distance (0–2, where smaller means more similar). This gives us a deterministic signal for relevance that exists before the model is ever called.

**Decision:**
Add a distance-based relevance filter in `retrieve()`. After `search()` returns results, drop any whose distance exceeds a threshold; return only what remains, which may be an empty list. The threshold is a module-level constant `RELEVANCE_THRESHOLD = 1.0`, exposed as a `threshold` parameter on `retrieve()` so it can be overridden per call. When retrieval returns nothing, `answer_query()` skips the model entirely and returns the fixed no-match message.

**Options considered:**
- A: Keep only the prompt-based (generation-side) defense. Simplest, but unreliable — it depends on the LLM and provides no guarantee.
- B: Add the distance filter inside `search()` in `vectorstore.py`. Rejected — relevance is a policy decision, and the storage layer should stay free of policy so it remains a dumb, reliable data layer.
- C: Add the distance filter in `retrieve()`, with the no-match decision in `answer_query()` (chosen). Retrieval reports what is relevant; generation decides what to do when nothing is.

**Rationale:**
Option C keeps each layer's job clean: `vectorstore.search()` reports what ChromaDB found (distances included), `retrieve()` applies the relevance policy, and `answer_query()` handles the empty case. The filter is deterministic — a number compared to a threshold — so it does not rely on the model the way the prompt rule does. The two defenses now complement each other: the distance cutoff catches "nothing is close enough," and the prompt rule catches "results are close-ish but don't actually answer." Skipping the model on an empty result is also an efficiency win, since there is no value in running an 8B model on CPU just to have it say it doesn't know.

The threshold value cannot be chosen by intuition. Cosine distances have no obvious good/bad boundary in the abstract — what counts as a strong match is specific to this corpus and embedding model. Observed strong matches so far cluster around 0.18–0.30, so a starting value of 1.0 is deliberately loose: it filters almost nothing, which avoids silently discarding real matches before there is evidence to set a tighter bound. A too-tight threshold would drop genuine incidents, which is worse than letting a few weak ones through at this stage.

**Consequences:**
- `retrieve()` may now return an empty list; callers must handle that. `answer_query()` does, by returning the no-match message without calling the model.
- `RELEVANCE_THRESHOLD` is the single named value Layer 3 evaluation will tune. The principled threshold comes from measuring retrieval quality at different cutoffs, not from guessing — turning a hardcoded placeholder into an evidence-backed setting.
- Tested deterministically: `test_retrieve_filters_by_threshold` confirms far results are dropped, and `test_answer_query_no_match_returns_message` confirms the model is skipped on empty retrieval (via `assert_not_called`).
- The threshold being a parameter, not just a constant, is what makes per-cutoff evaluation sweeps possible in Layer 3.