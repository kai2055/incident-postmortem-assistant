# ADR-019: Hosted Inference for Development, Local for Production

**Status:** Accepted
**Date:** 25 July 2026
**Relates to:** the call_llm seam introduced in Layer 2

---

## Context

Local inference on CPU is too slow to develop against. One Decompose call
measured 64 minutes. A full agent run took 101 minutes. Building an evaluation
set — which needs many runs — is impossible at that speed.

The cause is hardware, not code. Generating one token requires reading all 8
billion parameters (5.2GB) from RAM, so throughput is capped by memory bandwidth
at roughly 10 tokens/second on this laptop. A GPU has ~20× the bandwidth. The
Intel Arc GPU in this machine is not supported by Ollama's stack, so local
inference is stuck on CPU.

## Decision

Add a hosted provider to `call_llm`, selected by the `LLM_PROVIDER` environment
variable. Local Ollama remains the default and the supported production path.
Hosted inference (OpenRouter) is the development and evaluation path.

The model is `qwen/qwen3-8b` on OpenRouter — the **same weights** as the local
`qwen3:8b`. This is the deciding constraint: evaluating against a different or
larger model would produce numbers that do not transfer to the deployed system.

## The value proposition is intact

The project's claim is local inference: no per-query cost, no data leaving the
building, no vendor dependency — which matters for incident post-mortems, since
those documents contain an organisation's outage history and architecture.

Hosted inference does not break this, because:

- The model is open-weight. A firm can self-host it.
- A firm's deployment target is a GPU host, not a 16GB laptop. On an L4 or A10,
  qwen3:8b runs at 50–100 tokens/second and a full agent run finishes in under a
  minute. Local inference is unusable *on this hardware*, not unusable in
  principle.

So local is the product; hosted is the development environment. Same pattern as
developing against a small dataset and deploying against the real one.

## Measured result

Same trivial prompt, same weights:

| Path | Time |
|---|---|
| Local Ollama (CPU) | 600.3s |
| OpenRouter | 4.7s |

128× faster. The full 15-description symptom generation that would have taken
~20 hours locally took 2.9 minutes.

Cost is pay-per-token, no subscription, no idle charge. The entire Layer 2
workload is well under one dollar. A $2 per-key spend cap is set as a runaway
guard.

## Alternatives considered

**Disable reasoning locally (`/no_think`) and stay on CPU.** Worth doing anyway,
but even the fastest observed local call was 11 minutes. It does not make local
iteration viable.

**A different hosted model (gpt-oss-20b, qwen3.6-27b).** Rejected. A different
model breaks the transfer of evaluation numbers to the local deployment, which
is the whole point of matching weights.

**A closed model (GPT, Claude, Gemini).** Rejected outright. Not self-hostable,
which would break the local-inference value proposition.

## Consequences

Positive: development is 100×+ faster; evaluation sets and scoring runs become
practical; local production path unchanged; numbers transfer because weights
match.

Negative: development now depends on network access and a prepaid balance.
Secrets management added — `OPENROUTER_API_KEY` in `.env`, gitignored. Two new
dependencies (`requests`, `python-dotenv`).

## Open

- A reasoning toggle: keep `<think>` output as an observability feature in
  demo/production, disable it for evaluation throughput. The `call_llm` seam
  supports this; not yet wired.