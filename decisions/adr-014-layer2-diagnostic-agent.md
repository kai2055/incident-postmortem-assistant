# ADR-014: Layer 2 Diagnostic Agent Architecture

## Status

Accepted

## Context

Layer 1 is complete. The pipeline — ingest, chunk, embed, retrieve, generate — is built, tested, and calibrated to a 0.30 cosine distance threshold. The no-match defense is verified: three probes caught by distance, two by the generation layer's prompt-based decline.

Layer 2 needs to handle what Layer 1 cannot: messy, multi-symptom incident descriptions where the engineer hasn't yet isolated the root cause. A single retrieval on "API timing out, DB CPU spiking, auth errors" gets a blurry average. Layer 2 must decompose, retrieve per symptom, cross-reference, and produce a ranked differential diagnosis.

The project's core differentiator is measurable, inspectable reliability. Any agent framework must support stage-by-stage evaluation — not black-box looping where reasoning is hidden.

## Decision

Use LangGraph for the diagnostic agent, with explicit nodes, visible shared state, and a single conditional loop.

## Alternatives Considered

| Option | Why Rejected |
| --- | --- |
| LangChain agents | Black-box loop. Steps hidden inside the framework. Can't evaluate Decompose vs. Retrieve vs. Assess independently. |
| LlamaIndex agents | Same problem — higher-level, less visibility into intermediate reasoning. |
| Hand-rolled Python (while loop + dict) | Viable for this complexity. But conditional branching (loop back or diagnose) gets tangled fast as nodes grow. LangGraph's `add_conditional_edges` solves this cleanly. |
| No framework at all | Would work, but reinvents what LangGraph gives for free — state management, conditional routing, node isolation. |

### Why LangGraph Specifically

Node-level inspectability. Every node reads from and writes to a shared `DiagnosticState` dict. After any run, the full notebook is replayable: here's how it decomposed, here's what it retrieved each loop, here's why it looped or stopped, here's the final diagnosis. This directly supports the project's reliability thesis — "I measure every stage" — and is what lets Layer 3 later evaluate the agent stage by stage.

## State Design

```python
class DiagnosticState(TypedDict):
    original_query: str
    symptoms: list[str]
    retrieved: Annotated[dict[str, list[dict]], merge_retrieved]
    findings: str
    iterations: Annotated[int, operator.add]
    diagnosis: list[dict]
    sufficient: bool
    gap_reason: str
```

All fields initialized empty/present via `create_state()` — no node ever guards against a missing key. `diagnosis` is initialized as `[]` (structured list of candidates), not a prose string; this was corrected during the build when Diagnose was implemented to return `list[dict]` rather than text.

### Reducers

`retrieved`: `merge_retrieved` — latest-wins per symptom. When a gap-directed re-retrieval fires, new results for that symptom replace old ones. This is correct because re-retrieving a gap is trying to fill it (replace `[]` with evidence), not accumulate parallel trails.

`iterations`: `operator.add` — increments by 1 each loop pass. The cap is the safety net. (Note: the reducer only fires inside graph execution; direct node unit tests return `{"iterations": 1}` and do not accumulate, so accumulation to the cap is verified by the integration run, not the mocked suite.)

## Node Responsibilities

### Decompose

Reads `original_query`. Prompts the LLM to extract only explicitly-stated symptoms — no inference, no causes. Anti-hallucination guard baked into the prompt rules. Strips `<think>` tokens before parsing.

Returns: `{"symptoms": [...]}`

### Retrieve

Calls Layer 1's `retrieve()` per symptom, `top_k=3`. Empty lists (`[]`) are preserved, not dropped — they are the signal the sufficiency floor reads later ("this symptom has no evidence").

Returns: `{"retrieved": {...}, "iterations": 1}`

### Assess

Two jobs at completely different trust levels:

Job B — Mechanical floor (no LLM): Loop symptoms. If `not retrieved.get(symptom)` → uncovered. If any uncovered → `sufficient=False`, `gap_reason` names them. This is un-hallucinatable — the LLM cannot override it because no model touches it.

Job A — LLM cross-reference: Always runs, even when floor fails. Grounded prompt: reason only about retrieved incidents. Produces prose findings — which symptoms converge on the same incident, cause vs. effect. Always runs so findings is never empty going into a capped-final Diagnose.

Returns: `{"findings": "...", "sufficient": bool, "gap_reason": "..."}`

### Diagnose

Produces ranked differential diagnosis: list of `{cause, evidence, confidence}`.

Grounding hardening — the centerpiece of what the build taught:

The first integration test surfaced a real hole. The prompt said "grounded only," the parse checked `evidence != ""`, and the model produced two kinds of ungrounded output that both slipped through: it echoed the format header (`CAUSE | EVIDENCE | CONFIDENCE`) as a data row, and it invented `[INCIDENT_1]` as evidence. Both had non-empty strings in the evidence slot, so both passed the filter. Neither named an ID that existed in `retrieved`.

The fix: semantic grounding. Build a `valid_ids` set from actual retrieved chunks. After parsing the model's output, normalize each evidence string (strip brackets, split commas) and check intersection with `valid_ids`. If none match → the citation is hallucinated, drop the candidate. The same check kills both failures — the echoed header and the invented citation — because neither names a real retrieved ID. The fix is general, not a patch for one symptom.

Early exit: if `valid_ids` is empty (nothing retrieved for any symptom), return `[]` immediately — don't ask the model to diagnose from thin air.

Returns: `{"diagnosis": [...]}`

## The Conditional Fork (Hybrid Termination)

After Assess, `route_after_assess` reads state:

```python
if state["sufficient"] or state["iterations"] >= MAX_ITERATIONS:
    return "diagnose"
return "retrieve"
```

Two guards, two different failures:

Sufficiency prevents pointless extra loops when the picture is clear.

Cap (3 iterations) prevents infinite looping when the model's judgment or retrieval is stuck.

Both needed. Either alone is insufficient.

## What the Build Taught Us

The integration test — 55 minutes on CPU, 5 LLM calls — did two things.

First, it exposed the grounding hole. Syntactic grounding (`evidence != ""`) wasn't enough: the model obeyed the format instruction and produced plausible-looking evidence strings (an echoed header, an invented `[INCIDENT_1]`) that named nothing real. Only semantic grounding — checking citations against actual retrieved IDs — closed the hole. This mirrors ADR-013's arc: the threshold sweep found the filter bug because we measured; the integration test found the grounding bug because we ran the full loop.

Second, it surfaced a retrieval-empty result: the run retrieved nothing for any symptom, the agent looped to the cap, hit the early exit, and returned an honest empty diagnosis. The agent's behavior here is correct and confirmed — it declined rather than fabricated. What is *not* yet confirmed is the cause of the empty retrieval. A direct probe (`retrieve("database connection pool exhausted") → 0 []`) reproduced it in isolation against a populated store, which narrows it to two candidate causes, not yet distinguished:

- (a) Environmental — the embedder (`nomic-embed-text`) was not loaded during the run, so queries did not embed and nothing matched. A near-verbatim query returning zero from a populated store points here.
- (b) Retrieval-quality — decomposed symptom phrasing does not match corpus phrasing closely enough to clear the 0.30 threshold, even where related incidents exist.

These have different fixes and must not be conflated. Verification is pending an `ollama list` check and a re-run of the direct probe. Until then, the "agent declines honestly on a true no-match" framing is only half-established: the decline behavior is correct, but whether this particular empty was a *true* no-match or an embedder artifact is unresolved.

## Known Open

The retrieval-empty result is logged, not explained (see above — cause (a) vs (b) undistinguished, verification pending). The agent's honest-decline behavior on no evidence is accepted as correct regardless of which cause holds.

If (b) turns out to contribute, options exist (looser per-node threshold, higher `top_k`, rephrasing symptoms closer to corpus style) but each risks noise; none adopted yet.

The 55-minute integration runtime makes end-to-end testing a "run on demand" tier, not a CI gate — fast mocked unit tests are the actual quality gate.

## Consequences

Stage-by-stage evaluation is structurally supported. Can test Decompose output, Retrieve coverage, Assess sufficiency, Diagnose grounding independently.

The `valid_ids` grounding check is unit-testable: mock a diagnosis with fake evidence, assert it's filtered out.

Speed: integration tests hit Ollama multiple times; CI must rely on fast mocked unit tests.

The two-jobs split in Assess is the pattern to carry forward: mechanical floor the LLM can't override, plus LLM reasoning on top of a passing floor.