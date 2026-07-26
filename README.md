# Incident Post-Mortem Retrieval Assistant

A three-layer ML reliability pipeline that retrieves, diagnoses, and evaluates
engineering incident post-mortems to help engineers act faster during a live outage.

When a system goes down, the question is always the same: *has this happened
before, what was the root cause, how was it fixed?* Post-mortems hold those
answers but are buried in wikis and folders. This system makes them queryable in
plain language — institutional memory, made searchable.

Retrieving the wrong past incident during an outage sends an engineer chasing the
wrong root cause, so **the evaluation framework is the core of this project, not
an afterthought.** Every retrieval and generation decision is measured, tuned
against documented numbers, and gated in CI/CD.

---

## Status

| Layer | Description | State |
|-------|-------------|-------|
| **Layer 1 — RAG Pipeline** | ingest → chunk → embed → retrieve → generate | **Complete** |
| **Layer 2 — Diagnostic Agent** | multi-step symptom decomposition + dynamic retrieval → ranked differential diagnosis | **Early implementation** |
| **Layer 3 — Evaluation Agent** | auto-generated test queries + regression gating in CI/CD | **Designed, not yet built** |

---

## Architecture

**Layer 1 — RAG Pipeline (complete).**
Frontmatter ingestion, section-aware chunking with paragraph fallback, embedding,
a ChromaDB vectorstore layer (cosine distance), distance-threshold retrieval, and
grounded generation with numbered citations, a deterministic source list, and a
layered decline (both a retrieval-layer distance threshold and a generation-layer
grounded prompt — neither alone is sufficient).

**Layer 2 — Diagnostic Agent (early implementation).**
A LangGraph agent with four nodes — Decompose, Retrieve, Assess, Diagnose —
sharing a `DiagnosticState`. It accepts an incident description, decomposes it into
symptoms, issues retrievals per symptom (calling Layer 1 as a tool), cross-references
findings to distinguish root cause from downstream effect, and produces a ranked
differential diagnosis with evidence and confidence signals. Retrieval steps are
dynamic, not fixed: a hybrid termination condition stops when every symptom has
evidence *or* a hard iteration cap is hit, and gap reasons direct the next
retrieval rather than blindly retrying.

**Layer 3 — Evaluation Agent (designed).**
Triggers on every corpus change and CI/CD push, auto-generates synthetic test
queries from new documents, validates retrieval, runs regression checks against the
existing suite, gates deployment on metric thresholds, and emits a pass/fail report
with metric deltas.

---

## Stack

- **Language:** Python 3.12
- **Agent framework:** LangGraph — chosen over plain Python, LangChain agents,
  LlamaIndex, and CrewAI primarily for **inspectability**: every node writes to
  visible state, which is what makes stage-by-stage evaluation in Layer 3 possible.
- **Vector store:** ChromaDB (cosine distance)
- **Models (all local via Ollama):** `nomic-embed-text` (embeddings),
  `qwen3:8b` (generation), `deepseek-r1:8b` (agent layer). Ollama runs CPU-only.
- **Serving:** FastAPI + Docker → GCP Cloud Run
- **CI/CD:** GitHub Actions with metric-threshold deployment gates
- **Evaluation:** RAGAS + custom metric functions
- **Dev environment:** WSL2 / Ubuntu 24.04 (matched to the Cloud Run target)

---

## Corpus

**First-party post-mortems only** — no reconstructed or fictional incidents. Every
document is verified against its primary source and enforced to a 5-section schema
(Summary, Timeline, Root Cause, Resolution, Prevention).

Current corpus: **15 incidents → 82 chunks**, spanning 7 of 8 root-cause categories
(`agent-ai` intentionally empty — no findable first-party source).

- **By category:** configuration-error (3), human-error (3), database-storage (3),
  cascading-failure (2), credential-auth (2), network-bgp (1), supply-chain (1)
- **By severity:** 8 critical / 5 major / 1 minor

Ledger of committed documents: `data/incidents.csv`. Candidate incidents by
category gap: `corpus/backlog.md`.

---

## Evaluation

A **31-query ground-truth suite** (`data/eval/query_suite.json`) across five
difficulty tiers: easy (5), medium/symptom-phrased (12), hard/discrimination with
distractors (6), no-match calibration probes (5), and filter/set-scored (3).

**Metrics:** hit rate@k, MRR, section accuracy, decline rate, and set
precision/recall for filter queries. A hit is document-level primary,
section-level secondary.

**Current results** (retrieval distance threshold tuned to 0.30, ADR-013):

| Metric | Value |
|--------|-------|
| Decline rate | 0.600 |
| Hit rate | 1.000 |
| MRR | 0.949 |
| Section accuracy | 0.435 |

The 0.30 threshold is a strict improvement over the 1.0 placeholder — better
decline behavior with no cost to retrieval metrics.

---

## API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/query` | Layer 1 retrieval + grounded generation |
| `POST` | `/diagnose` | Layer 2 differential diagnosis from an incident description |
| `GET`  | `/evaluate` | Run the evaluation suite |
| `GET`  | `/health` | System health + last eval status |

---

## Setup (WIP)

1. Install Ollama and pull the models:
   `ollama pull nomic-embed-text && ollama pull qwen3:8b && ollama pull deepseek-r1:8b`
2. Install dependencies: `pip install -r requirements.txt`
3. Run ingestion: `python src/ingestion.py`
4. Start the API: `uvicorn src.api:app --reload`

---

## Design decisions

Every significant architectural decision is recorded as an ADR with its reasoning,
the alternatives considered, and the bugs found along the way. ADR-001 through
ADR-013 are documented, including the threshold-tuning evidence trail and the
deferred-MLflow decision.

## License

MIT