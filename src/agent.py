from typing import TypedDict, Annotated
import re
import operator

from langgraph.graph import StateGraph, START, END
from src.generation import call_llm
from src.embedding import retrieve  # Layer 1 retriever, calibrated to 0.30 threshold


# ── Helpers ──────────────────────────────────────────────────────────────

def strip_think(text: str) -> str:
    """
    Remove qwen3/deepseek reasoning blocks.

    Extracted so the regex exists in exactly one place. It was previously
    inlined in three nodes and mistyped repeatedly on retype — a leading
    space made it silently never fire, letting reasoning text through as data.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def merge_retrieved(old: dict, new: dict) -> dict:
    """
    Reducer: merge per-loop retrieval results. Latest-wins per symptom -
    a gap-directed re-retrieve fills the hole rather than stacking history.
    """
    return {**old, **new}


# ── State ────────────────────────────────────────────────────────────────

class DiagnosticState(TypedDict):
    original_query: str
    symptoms: list[str]
    retrieved: Annotated[dict[str, list[dict]], merge_retrieved]  # symptom -> incident dicts
    findings: str
    iterations: Annotated[int, operator.add]
    diagnosis: list[dict]
    sufficient: bool
    gap_reason: str


def create_state(original_query: str) -> DiagnosticState:
    return {
        "original_query": original_query,
        "symptoms": [],
        "retrieved": {},
        "findings": "",
        "iterations": 0,
        "diagnosis": [],
        "sufficient": False,
        "gap_reason": "",
    }


# ── Node 1: Decompose ────────────────────────────────────────────────────

def decompose_node(state: DiagnosticState) -> dict:
    """
    Break the incident description into distinct symptoms.

    Extracts only symptoms explicitly stated in the query.
    No inference, no addition - what the engineer saw, not what
    might be happening.
    """

    query = state["original_query"]

    prompt = f"""You are a diagnostic assistant. Your job is to read an engineer's incident
    description and extract only the symptoms they explicitly report.

    ## Rules

    1. **Only what's stated.** Extract symptoms the engineer actually describes.
    Do not infer causes, do not add symptoms that aren't mentioned, do not interpret.

    2. **One symptom per line.** Each symptom is a single line of plain text.
    No numbering, no bullets, no preamble, no conclusion.

    3. **Symptoms only, not causes.** "Database CPU spiked" is a symptom.
    "Database CPU spiked because of a bad query" is interpretation - drop the
    "because" part.

    4. **If the description is vague, extract what you can.**
    A single vague symptom is better than inventing specifics.

    ## Incident Description

    {query}

    ## Symptoms

    """

    raw_response = call_llm(prompt)
    cleaned = strip_think(raw_response)

    # Parse: drop empties and preambles, strip list markers, keep the rest.
    # The prompt forbids bullets and preamble; the model adds them anyway.
    symptoms = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Skip preamble lines (e.g. "Here are the symptoms:")
        if line.endswith(":"):
            continue

        # Strip list markers only. A digit counts as a marker only when
        # followed by '.' or ')' AND then whitespace or end of line, so
        # "500 errors", "3.5 second latency" and "502s" survive intact.
        # The '|$' branch catches a bare "-" with no text after it.
        line = re.sub(r"^(?:[-*•]|\d+[.)])(?:\s+|$)", "", line).strip()
        if not line:
            continue

        symptoms.append(line)

    return {"symptoms": symptoms}


# ── Node 2: Retrieve ─────────────────────────────────────────────────────

def retrieve_node(state: DiagnosticState) -> dict:
    """
    Retrieve past incidents for each decomposed symptom.

    Calls the calibrated Layer 1 retriever per symptom. Empty results are
    preserved as [] - they are the signal the sufficiency check reads later.

    top_k is deliberately not passed: the node inherits DEFAULT_TOP_K from
    retrieve(). It previously hardcoded 3, meaning the agent saw less
    evidence per symptom than a single Layer 1 query does. See ADR-015.
    """
    symptoms = state["symptoms"]
    retrieved: dict[str, list[dict]] = {}

    for symptom in symptoms:
        results = retrieve(symptom)
        retrieved[symptom] = results  # [] is meaningful: "no evidence for this symptom"

    # Loop-safety is handled by the merge_retrieved reducer on the state field,
    # so a gap-directed re-retrieve replaces that symptom's entry rather than
    # discarding results for symptoms not re-queried this pass.
    return {"retrieved": retrieved, "iterations": 1}


# ── Node 3: Assess ───────────────────────────────────────────────────────

def assess_node(state: DiagnosticState) -> dict:
    """
    Cross-reference retrieved incidents and judge sufficiency against state.

    Two jobs, kept separate:
        - Job B (mechanical floor): every symptom must have non-empty evidence.
            No LLM. Un-hallucinatable.
        - Job A (LLM): grounded cross-reference prose - which symptoms converge
            on the same incidents, which is cause vs effect. Always runs so
            findings is never empty into a capped-final Diagnose.
    """
    symptoms = state["symptoms"]
    retrieved = state["retrieved"]

    # Job B: mechanical floor
    uncovered: list[str] = []
    for symptom in symptoms:
        if not retrieved.get(symptom):  # catches [] and missing key
            uncovered.append(symptom)

    if uncovered:
        sufficient = False
        gap_reason = f"No evidence for: {','.join(uncovered)}"
    else:
        sufficient = True
        gap_reason = ""

    # Job A: LLM cross-reference
    # Grounded prompt: symptom -> incidents actually retrieved
    evidence_lines: list[str] = []
    for symptom in symptoms:
        hits = retrieved.get(symptom, [])
        if hits:
            incident_summaries = []
            for h in hits:
                # Minimal readable summary from the chunk dict
                doc_id = h.get("id", "unknown")
                distance = h.get("distance", "N/A")
                text_preview = h.get("text", "")[:120].replace("\n", " ")
                incident_summaries.append(
                    f'  - {doc_id} (dist {distance}): "{text_preview}..."'
                )
            evidence_lines.append(f"Symptom: {symptom}\n" + "\n".join(incident_summaries))
        else:
            evidence_lines.append(f"Symptom: {symptom}\n (no incidents retrieved)")

    evidence_block = "\n\n".join(evidence_lines)

    prompt = f"""You are a diagnostic assistant reviewing evidence retrieved for an ongoing incident.


    ## Rules
    1. **Grounded only.** Reason only about the incidents listed below. Do not invent incidents or draw on general knowledge of outages.
    2. **Cross-reference.** For each symptom, note which past incident(s) match. Then ask: do multiple symptoms point at the same underlying
        incident? If so, which symptom is likely the root cause and which are downstream effects?
    3. **Be concise.** A short paragraph of findings is enough. No preamble, no conclusion.

    ## Original Incident Description
    {state['original_query']}

    ## Retrieved Evidence Per Symptom
    {evidence_block}


    ## Findings

"""

    raw_findings = call_llm(prompt)
    findings = strip_think(raw_findings)

    return {"findings": findings, "sufficient": sufficient, "gap_reason": gap_reason}


# ── Node 4: Diagnose ─────────────────────────────────────────────────────

def diagnose_node(state: DiagnosticState) -> dict:
    """
    Produce a grounded, ranked differential diagnosis.

    Every candidate cause must trace to a real retrieved incident.
    Confidence comes from evidence convergence, not the model's gut feeling.
    """
    findings = state["findings"]
    retrieved = state["retrieved"]

    # Build the set of incident IDs actually retrieved. This is the ground
    # truth the model's citations are checked against - syntactic citation
    # format is not enough, the integration run proved qwen3 will invent
    # well-formed IDs that were never retrieved.
    valid_ids = set()
    for hits in retrieved.values():
        for h in hits:
            if doc_id := h.get("id"):
                valid_ids.add(doc_id)

    # Early exit: no real evidence -> do not ask the model to hallucinate
    if not valid_ids:
        return {"diagnosis": []}

    evidence_lines: list[str] = []
    for symptom, hits in retrieved.items():
        if hits:
            doc_ids = [h.get("id", "unknown") for h in hits]
            evidence_lines.append(f"    {symptom}: {', '.join(doc_ids)}")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else " (no evidence retrieved)"

    prompt = f"""You are a diagnostic assistant producing a final ranked differential diagnosis.


    ## Rules
    1. **Grounded only.** Every candidate root cause must be backed by a specific retrieved incident listed below. Do not
    invent causes or draw on general knowledge.
    2. **Rank by evidence convergence.** A cause supported by multiple symptoms is higher confidence than one supported by a single symptom.
    Confidence must reflect evidence strength, not your personal certainty.
    3. **One candidate per line.** Format each as: CAUSE | EVIDENCE | CONFIDENCE
        - CAUSE: short description of the root cause candidate
        - EVIDENCE: the incident ID(s) that support it
        - CONFIDENCE: high / medium / low (based on how many symptoms converge)
    4. **No preamble, no conclusion.** Output only the ranked lines.


    ## Findings from Cross-Reference
    {findings}

    ## Available Retrieved Evidence
    {evidence_block}

    ## Ranked Differential Diagnosis

        """
    raw_response = call_llm(prompt)
    cleaned = strip_think(raw_response)

    diagnosis: list[dict] = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Skip header echo - model sometimes repeats the format instruction
        if line.replace(" ", "").upper() == "CAUSE|EVIDENCE|CONFIDENCE":
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            diagnosis.append({
                "cause": parts[0],
                "evidence": parts[1],
                "confidence": parts[2].lower(),
            })
        elif len(parts) == 2:
            diagnosis.append({
                "cause": parts[0],
                "evidence": parts[1],
                "confidence": "unknown",
            })
        elif len(parts) == 1:
            diagnosis.append({
                "cause": parts[0],
                "evidence": "",
                "confidence": "unknown",
            })

    # Hardened grounding: evidence must cite at least one real retrieved ID
    grounded: list[dict] = []
    for d in diagnosis:
        cited = {
            x.strip()
            for x in d["evidence"].replace("[", "").replace("]", "").split(",")
            if x.strip()
        }
        if cited & valid_ids:
            grounded.append(d)
        # else: hallucinated evidence, drop it

    return {"diagnosis": grounded}


# ── Graph ────────────────────────────────────────────────────────────────

MAX_ITERATIONS = 3


def route_after_assess(state: DiagnosticState) -> str:
    """
    Hybrid termination: sufficient OR capped -> diagnose, else loop back.
    """
    if state["sufficient"] or state["iterations"] >= MAX_ITERATIONS:
        return "diagnose"
    return "retrieve"


def build_diagnostic_graph():
    """
    Assemble the four nodes into a LangGraph StateGraph with the conditional loop.
    """
    builder = StateGraph(DiagnosticState)

    builder.add_node("decompose", decompose_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("assess", assess_node)
    builder.add_node("diagnose", diagnose_node)

    builder.add_edge(START, "decompose")
    builder.add_edge("decompose", "retrieve")
    builder.add_edge("retrieve", "assess")

    builder.add_conditional_edges(
        "assess",
        route_after_assess,
        {"retrieve": "retrieve", "diagnose": "diagnose"},
    )

    builder.add_edge("diagnose", END)

    return builder.compile()