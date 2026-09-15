# Observability Plan — Incident Post-Mortem Retrieval Assistant

A plan to add observability to the system, turning the offline evaluation gate into online, live-traffic monitoring. Written as a design doc to work through before building.

---

## Why this, why now

The evaluation gate (Layer 3) already answers *"did this change make the system worse?"*—offline, on a schedule. Observability is the **online** version of the same question: *"is the system getting worse right now, on live traffic, before anyone complains?"*

This is a deliberate gap-fill. The role postings this targets (ML / MLOps / reliability, Berlin market) repeatedly ask for exactly this: monitoring, alerting, and "detecting silent model degradation before it affects business metrics." The project is already unusually strong on offline evaluation—most portfolios aren't. Observability extends that strength into the live dimension the market asks for, and it does so by reusing concepts already built rather than learning new ones.

**Key framing:** the quality metrics already exist (grounding violations, decline rate, retrieval distances, iteration counts). Observability is instrumenting them as *live signals* instead of *offline checks*. Same metrics, different timing.

---

## Two layers of observability

**1. Ops observability (the generic half).**  
Standard service metrics: request latency, error rate, throughput per endpoint. This is the "understands latency, error handling, observability basics" that postings list. Given the CPU-bound inference, latency is genuinely worth seeing as a graph—a diagnosis call can take 100+ seconds locally.

**2. LLM / eval observability (the differentiator half).**  
Instrument the *quality* signals on live traffic—the online mirror of the gate:
- grounding violations (must stay 0—alert on any),
- decline rate over real queries,
- retrieval distances and how often the correct-looking match is weak,
- how often the agent hits its iteration cap,
- per-node latency and token counts.

This is the part that reads as "silent model degradation detection," and it's where the project's existing eval work pays off.

---

## Tooling—three pieces, in dependency order

### Piece 1—LangSmith tracing (start here, no deployment needed)

LangSmith hooks directly into the LangGraph agent and traces every node (Decompose → Retrieve → Assess → Diagnose) with timing, inputs/outputs, and token counts. This is the cheapest, highest-fit first step because:

- it needs **no deployment**—it instruments the agent as it already runs,
- it's a **natural fit** for the LangGraph design, which was chosen precisely for node-level inspectability,
- it directly matches the "LLM observability with LangSmith" phrasing in the target job postings.

**What it gives:** a visual trace of each diagnosis—which node was slow, what each node retrieved, where an iteration loop happened, how many tokens each step cost. Immediately useful for understanding the agent's behaviour, and a strong demo artifact.

**Effort:** low. LangSmith integrates with LangGraph via environment variables and a decorator/callback; minimal code change.

### Piece 2—Prometheus + Grafana on the FastAPI service (needs the service running)

Once the pipeline is wrapped in a FastAPI service (see the deployment plan), instrument it with Prometheus metrics and visualise in Grafana:

- request latency histograms per endpoint (`/query`, `/diagnose`),
- error rate and status-code distribution,
- throughput,
- inference call durations (embedding + generation), which given CPU-bound local inference are the dominant latency.

**Dependency:** this needs a live service to scrape, which means the FastAPI + Docker step must exist first (even running locally in a container is enough—it doesn't require cloud deployment). So this comes *after* the service is built.

**Effort:** moderate. A Prometheus client library exposes a `/metrics` endpoint; Prometheus scrapes it; Grafana dashboards read from Prometheus. Standard, but several moving parts.

### Piece 3—Eval-signals dashboard (the differentiator)

A Grafana dashboard of the *evaluation* metrics as live signals:
- **grounding violations**—a panel that should read 0, with an alert that fires on any non-zero value. This is the online twin of the hard invariant in the offline gate.
- **decline rate** on live traffic—trending up could mean the corpus no longer covers what people ask.
- **iteration-cap hits**—how often the agent exhausts its loop without resolving.
- **retrieval distance distribution**—drift here is an early sign of the corpus or embedder degrading.

**Why this is the payoff:** a panel showing grounding violations ticking above 0 on live traffic—*before* anyone reports a bad answer—is "stays working" made visible. It's the offline gate's logic, running continuously.

**Dependency:** needs Pieces 1–2 in place (the service running and instrumented).

---

## Recommended sequencing

1. **LangSmith tracing**—now, no deployment needed, high signal, natural fit. This alone is a strong observability addition and a good demo.
2. **FastAPI service + Docker**—the enabler for the metrics layer (and the deployment arc generally). This also forces the hosted-embedding decision.
3. **Prometheus + Grafana ops metrics**—once the service runs.
4. **Eval-signals dashboard + grounding alert**—the differentiator, built on top of the metrics layer.

LangSmith is the clear first move: it's decoupled from deployment, it instruments the thing already built, and it demonstrates the exact skill the market names. Everything after it naturally motivates the deployment work, so observability and deployment become one arc rather than two separate efforts.

---

## Honest scoping notes

- **The metrics layer depends on a running service.** Prometheus scrapes a live endpoint; there's nothing to scrape until the FastAPI service exists. So the ops-metrics and eval-dashboard pieces can't come before the service, even locally. LangSmith is the exception—it needs no service.
- **Live eval signals aren't a full offline eval.** Observability watches signals on whatever traffic arrives; it doesn't run the ground-truth query suite. It complements the offline gate (which uses ground truth) rather than replacing it. Both matter: the gate proves correctness against known answers; the dashboard watches for drift on unknown live queries.
- **What "business metrics" would mean here.** The postings talk about degradation before it affects business metrics. In this system the closest analogue is engineer trust—a wrong retrieval during an outage. The grounding-violation alert is the most direct proxy for "the system is about to mislead someone."

---

## Interview framing

The one-line story: *"The system has an offline regression gate that proves correctness against ground truth, and online observability that watches the same quality signals on live traffic—so degradation is caught both before a change ships and after it's live."* That pairing—offline gate plus online monitoring, both driven by the same consequence-based reasoning—is the complete reliability story, and it maps directly onto what the role asks for.