# ADR-016: Layer 2 Diagnostic Agent Design

**Status:** Accepted. Implementation complete, calibration unresolved.
**Date:** 24 July 2026
**Relates to:** ADR-014 (Layer 2 handoff), ADR-015 (candidate depth)

---

## Context

Layer 1 answers one question at a time. An engineer types a query, gets
matching post-mortems back.

A real outage is not one question. The engineer sees several things at once —
errors, latency, a saturated resource — and does not know which is the cause
and which is the effect. Asking Layer 1 three separate questions and reading
three separate answers puts the cross-referencing work back on the person who
is already under pressure.

Layer 2 does that work: split the description into symptoms, retrieve for each,
check whether the evidence is enough, and produce a ranked differential
diagnosis where every candidate cause traces to a real retrieved incident.

---

## Decision 1: LangGraph, not LangChain agents or LlamaIndex

LangGraph 1.2.5, using `StateGraph` with a `TypedDict` state.

The deciding factor is **node-level inspectability**. Layer 3 has to evaluate
the agent stage by stage — did Decompose extract the right symptoms, did
Retrieve find evidence, did Assess judge sufficiency correctly. That requires
reading intermediate state, not just the final answer.

LangChain's agent abstractions and LlamaIndex's query engines both hide the
intermediate steps behind a single call. Every node here writes to a state
object that can be read directly, which is what makes stage-by-stage evaluation
possible at all.

This is a deliberate architectural choice driven by the evaluation requirement,
not a default.

---

## Decision 2: Four nodes with a conditional loop

```
START -> decompose -> retrieve -> assess -> [conditional] -> diagnose -> END
                          ^                      |
                          +----------------------+
```

**Decompose** — split the description into symptoms.
**Retrieve** — one Layer 1 call per symptom.
**Assess** — judge whether the evidence is sufficient.
**Diagnose** — produce the ranked differential.

The loop exists because the first retrieval pass may leave a symptom with no
evidence. Rather than diagnosing on a partial picture, the graph goes back and
retrieves again.

---

## Decision 3: State reducers

Two fields need reducers because the loop writes to them more than once.

```python
retrieved: Annotated[dict[str, list[dict]], merge_retrieved]
iterations: Annotated[int, operator.add]
```

**`merge_retrieved` is latest-wins per symptom:**

```python
def merge_retrieved(old: dict, new: dict) -> dict:
    return {**old, **new}
```

A second pass is gap-directed — it re-retrieves for symptoms that came back
empty. Latest-wins means that pass fills the hole without discarding results
for symptoms it did not re-query. Stacking history instead would grow the
evidence block on every loop and make the Assess prompt longer each time for no
benefit.

**`operator.add` on `iterations`** because each pass through Retrieve returns
`{"iterations": 1}` and the reducer accumulates. The node does not need to know
the current count, which keeps it stateless.

---

## Decision 4: Assess does two jobs, kept separate

This is the most important design decision in Layer 2.

**Job B — the mechanical floor. No LLM.**

```python
uncovered = [s for s in symptoms if not retrieved.get(s)]
sufficient = not uncovered
```

Every symptom must have non-empty evidence. `.get()` with a falsy check catches
both `[]` and a missing key. This cannot be hallucinated, argued with, or
overridden by the model.

**Job A — the LLM cross-reference.** Which symptoms converge on the same
incident, which is cause and which is effect. Prose, written into `findings`.

The split matters because the two questions have different reliability
requirements. "Is there evidence for every symptom?" is a counting question
with a correct answer — a language model should not be asked. "Which symptom is
downstream of which?" is genuinely interpretive and worth a model.

If sufficiency were left to the LLM, it could declare itself satisfied with no
evidence at all, and the loop would never fire.

**Job A always runs, even when the floor fails.** If the graph hits the
iteration cap while still insufficient, Diagnose must still receive non-empty
findings rather than an empty string.

The gap reason names the specific symptoms:

```python
gap_reason = f"No evidence for: {','.join(uncovered)}"
```

That specificity is what makes a re-retrieval gap-directed rather than a blind
repeat.

---

## Decision 5: Hybrid termination

```python
MAX_ITERATIONS = 3

def route_after_assess(state) -> str:
    if state["sufficient"] or state["iterations"] >= MAX_ITERATIONS:
        return "diagnose"
    return "retrieve"
```

Two independent stop conditions: the sufficiency judgment, or the iteration cap.

The cap is the guarantee. Sufficiency depends on retrieval succeeding, and if
retrieval systematically fails, sufficiency never becomes true. Without the cap
the graph would loop forever. With it, the worst case is bounded and the agent
produces the best answer it can from what it has.

This is not hypothetical — the 24 July integration run hit the cap on all three
iterations because nothing cleared the relevance threshold. The cap was the only
thing that ended the run.

---

## Decision 6: Grounding is verified against retrieved IDs, not citation format

The first integration run exposed two failures that syntactic checking would
have missed. qwen3 echoed the format header `CAUSE | EVIDENCE | CONFIDENCE`
back as a data row, and it emitted citations like `[INCIDENT_1]` for incidents
that were never retrieved. Both were correctly formatted. Both were fabricated.

The fix builds the set of valid IDs from what was actually retrieved, and
requires an intersection:

```python
valid_ids = set()
for hits in retrieved.values():
    for h in hits:
        if doc_id := h.get("id"):
            valid_ids.add(doc_id)

# ...

cited = {x.strip() for x in d["evidence"].replace("[", "").replace("]", "").split(",") if x.strip()}
if cited & valid_ids:
    grounded.append(d)
```

A candidate whose cited IDs do not intersect the retrieved set is dropped
silently. There is also an early exit: if `valid_ids` is empty, the node returns
`{"diagnosis": []}` **without calling the model at all** — asking it to produce
a diagnosis with no evidence is an invitation to invent one.

The principle: **checking that a citation looks right is not checking that it is
right.**

---

## Decision 7: Parser hardening in Decompose

The prompt forbids preamble, bullets and numbering. The model produces them
anyway. Prompt instructions are a request, not a constraint, so the parser has
to be defensive.

Three rules:

```python
if line.endswith(":"):
    continue

line = re.sub(r"^(?:[-*•]|\d+[.)])(?:\s+|$)", "", line).strip()
if not line:
    continue
```

**Colon-ending lines are skipped** — catches "Here are the symptoms:". Without
this, the preamble became a symptom, was searched against the corpus, returned
nothing, and Assess counted it as an uncovered symptom, forcing a pointless
loop.

**The marker regex requires a delimiter and then whitespace or end of line.**
A digit only counts as a list marker when followed by `.` or `)` and then a
space. This is deliberately narrow: a greedy version like `^[-*\d.)]+\s*` would
turn "500 errors returned by API" into "errors returned by API" and "502s
across all edge nodes" into "s across all edge nodes" — silently deleting the
details that matter most in an incident corpus. Covered by
`test_decompose_preserves_numbers_in_symptom_text`.

**The `|$` branch** catches a bare `-` with no text, which would otherwise
survive as a one-character symptom.

**Known limitation:** trailing commentary such as "These are the main issues."
is still kept. It has no colon and no marker, so nothing distinguishes it from
a symptom. Asserted in `test_decompose_mixed_formatting` rather than hidden.

---

## Alternatives considered

**LLM-only sufficiency judgment.** Rejected. The model can declare itself
satisfied with no evidence, which disables the loop entirely.

**Mechanical-only assessment, no LLM in Assess.** Rejected. Cross-referencing
which symptoms converge on the same incident is genuinely interpretive, and
Diagnose needs that prose.

**Stacking retrieval history instead of latest-wins.** Rejected. Grows the
prompt on every loop for no diagnostic benefit, and CPU inference is already the
bottleneck.

**Citation-format validation only.** Rejected by evidence — the integration run
produced well-formed fabricated citations.

**No iteration cap, terminate on sufficiency alone.** Rejected. Sufficiency
depends on retrieval succeeding. When retrieval fails systematically, the graph
never terminates.

---

## Consequences

**Positive.** Every node writes inspectable state, which is what Layer 3
requires. Sufficiency cannot be hallucinated. Fabricated citations cannot reach
the output. Termination is guaranteed. 29 unit tests cover all four nodes and
run in 0.19 seconds against mocked `call_llm`.

**Negative — cost.** Five sequential qwen3 calls on CPU. The end-to-end run
took 55 minutes at `top_k=3`, and 101 minutes after ADR-015 raised it to 10 —
longer evidence blocks mean longer prompts, and prompt length is what CPU
inference charges for. This is not merely inconvenient: a component that takes
90 minutes per run cannot be iterated on, which is why inference speed is now
a prerequisite for building the Layer 2 evaluation set rather than a
nice-to-have.

**Negative — calibration.** Documented separately, but it belongs in the
consequences: the agent currently retrieves nothing. Decompose is instructed to
preserve the engineer's wording, engineers write plain English, and plain
English measures 0.32–0.41 against this corpus while the threshold keeps 0.30
and below. In the 24 July run all three symptoms failed, including one where
`github-database-2018-10-21:root_cause:0` — the correct document — was ranked
first at 0.3215 and discarded by 0.0215.

The design is sound. The calibration between Layer 1 and Layer 2 is not.

---

## Open items

- Layer 2 needs its own relevance threshold, calibrated against the symptom
  strings Decompose actually generates rather than against hand-written queries
- No Layer 2 evaluation set exists — the blocking item
- Inference speed: `/no_think`, `keep_alive: -1`, or a smaller model via the
  existing `call_llm(model=...)` seam
- Near-miss reporting from `retrieve()` would have made the empty 101-minute
  run diagnosable in seconds

  