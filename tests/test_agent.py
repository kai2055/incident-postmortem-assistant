from unittest.mock import patch

from src.agent import (
    strip_think,
    create_state,
    decompose_node,
    retrieve_node,
    assess_node,
    diagnose_node,
    route_after_assess,
    MAX_ITERATIONS,
    LAYER2_THRESHOLD,
)


# ── strip_think helper ───────────────────────────────────────────────────

def test_strip_think_removes_block():
    assert strip_think("<think>reasoning</think>answer") == "answer"


def test_strip_think_multiline():
    text = "<think>\nline one\nline two\n</think>\nthe answer"
    assert strip_think(text) == "the answer"


def test_strip_think_no_block_is_passthrough():
    assert strip_think("just an answer") == "just an answer"


def test_strip_think_at_position_zero():
    """
    Regression guard: a leading space in the regex made this silently never
    fire, letting the entire reasoning block through as data.
    """
    assert strip_think("<think>hmm</think>real output") == "real output"


# ── Node 1: Decompose ────────────────────────────────────────────────────

def test_decompose_clean_response():
    """Clean response parses into a list of symptoms."""
    state = create_state("Our API is timing out and the database CPU is spiking.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API is timing out\ndatabase CPU is spiking"
        result = decompose_node(state)

    assert result == {"symptoms": ["API is timing out", "database CPU is spiking"]}
    mock_llm.assert_called_once()


def test_decompose_strips_think_tokens():
    """Reasoning blocks are removed before parsing."""
    state = create_state("Users cannot log in and payments are failing.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "<think>\n"
            "Let me extract the symptoms from this description.\n"
            "</think>\n"
            "Users cannot log in\n"
            "payments are failing"
        )
        result = decompose_node(state)

    assert result == {"symptoms": ["Users cannot log in", "payments are failing"]}


def test_decompose_skips_preamble():
    """Lines ending in ':' are dropped."""
    state = create_state("Service is down and latency is high.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "Here are the symptoms:\n"
            "- Service is down\n"
            "- Latency is high"
        )
        result = decompose_node(state)

    assert result == {"symptoms": ["Service is down", "Latency is high"]}


def test_decompose_strips_bullet_markers():
    state = create_state("Database slow and 500 errors.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "- database slow\n"
            "* 500 errors returned by API\n"
            "• CPU at 100%"
        )
        result = decompose_node(state)

    assert result == {
        "symptoms": ["database slow", "500 errors returned by API", "CPU at 100%"]
    }


def test_decompose_strips_number_markers():
    state = create_state("Database slow and 500 errors.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "1. database slow\n"
            "2) 500 errors returned by API\n"
            "3. CPU at 100%"
        )
        result = decompose_node(state)

    assert result == {
        "symptoms": ["database slow", "500 errors returned by API", "CPU at 100%"]
    }


def test_decompose_preserves_numbers_in_symptom_text():
    """
    Regression guard. An over-greedy marker regex deletes the numbers that
    matter most - '500 errors' becomes 'errors', '502s' becomes 's'.
    """
    state = create_state("API returning 500s and 3.5 second latency.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "500 errors returned by API\n"
            "3.5 second latency spike\n"
            "502s across all edge nodes\n"
            "100% CPU usage"
        )
        result = decompose_node(state)

    assert result == {
        "symptoms": [
            "500 errors returned by API",
            "3.5 second latency spike",
            "502s across all edge nodes",
            "100% CPU usage",
        ]
    }


def test_decompose_marker_vs_decimal():
    """'3. ' is a marker and is stripped; '3.5' is text and survives."""
    state = create_state("Database issues.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "3. database slow\n3.5 second latency"
        result = decompose_node(state)

    assert result == {"symptoms": ["database slow", "3.5 second latency"]}


def test_decompose_drops_empty_and_bare_markers():
    """A bare '-' with no text must not become a symptom."""
    state = create_state("Service down.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "\n"
            "Service is down\n"
            "\n"
            "- \n"
            "\n"
            "Latency is high\n"
        )
        result = decompose_node(state)

    assert result == {"symptoms": ["Service is down", "Latency is high"]}


def test_decompose_mixed_formatting():
    """
    Realistic messy response. Note the trailing commentary line IS kept -
    it has no colon and no marker, so nothing distinguishes it from a
    symptom. Known limitation, asserted rather than hidden.
    """
    state = create_state("Everything is broken.")

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "<think>\nComplex incident.\n</think>\n"
            "Here are the symptoms:\n"
            "\n"
            "1. 500 errors on all endpoints\n"
            "\n"
            "- database connection timeouts\n"
            "\n"
            "* 3.5 second latency on checkout\n"
            "\n"
            "2) 100% CPU on primary node\n"
            "\n"
            "These are the main issues.\n"
        )
        result = decompose_node(state)

    assert result == {
        "symptoms": [
            "500 errors on all endpoints",
            "database connection timeouts",
            "3.5 second latency on checkout",
            "100% CPU on primary node",
            "These are the main issues.",
        ]
    }


# ── Node 2: Retrieve ─────────────────────────────────────────────────────

def test_retrieve_node_normal():
    """One retrieve call per symptom, results keyed by symptom."""
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]

    with patch("src.agent.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = [
            [{"id": "incident-a", "distance": 0.25}],
            [{"id": "incident-b", "distance": 0.22}],
        ]
        result = retrieve_node(state)

    assert result == {
        "retrieved": {
            "API timeout": [{"id": "incident-a", "distance": 0.25}],
            "DB CPU spike": [{"id": "incident-b", "distance": 0.22}],
        },
        "iterations": 1,
    }
    assert mock_retrieve.call_count == 2


def test_retrieve_node_call_signature():
    """
    Two decisions locked in here.

    top_k is NOT passed - the node inherits DEFAULT_TOP_K. It previously
    hardcoded 3, giving the agent less evidence per symptom than a single
    Layer 1 query (ADR-015).

    threshold IS passed - Layer 2 uses its own looser value. Decompose
    produces symptom fragments scoring 0.32-0.41, while Layer 1's 0.30 was
    tuned on complete questions at 0.20-0.27. Inheriting the default meant
    every result was discarded and the agent started with no evidence.
    """
    state = create_state("API timeout")
    state["symptoms"] = ["API timeout"]

    with patch("src.agent.retrieve") as mock_retrieve:
        mock_retrieve.return_value = [{"id": "incident-a", "distance": 0.25}]
        retrieve_node(state)

    mock_retrieve.assert_called_once_with("API timeout", threshold=LAYER2_THRESHOLD)


def test_retrieve_node_preserves_empty():
    """A symptom with no matches keeps its key with [], it is not dropped."""
    state = create_state("DDoS attack on CDN")
    state["symptoms"] = ["DDoS attack", "CDN latency"]

    with patch("src.agent.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = [
            [],  # threshold filtered everything
            [{"id": "incident-c", "distance": 0.20}],
        ]
        result = retrieve_node(state)

    assert result["retrieved"]["DDoS attack"] == []
    assert result["retrieved"]["CDN latency"] == [{"id": "incident-c", "distance": 0.20}]


def test_retrieve_node_empty_symptoms():
    """No symptoms means no calls and no crash."""
    state = create_state("nothing specific")
    state["symptoms"] = []

    with patch("src.agent.retrieve") as mock_retrieve:
        result = retrieve_node(state)

    assert result == {"retrieved": {}, "iterations": 1}
    mock_retrieve.assert_not_called()


# ── Node 3: Assess ───────────────────────────────────────────────────────

def test_assess_floor_all_covered():
    """Every symptom has evidence -> sufficient, no gap."""
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]
    state["retrieved"] = {
        "API timeout": [{"id": "incident-a", "distance": 0.25}],
        "DB CPU spike": [{"id": "incident-b", "distance": 0.22}],
    }

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "Both symptoms map to past incidents"
        result = assess_node(state)

    assert result["sufficient"] is True
    assert result["gap_reason"] == ""
    assert result["findings"] == "Both symptoms map to past incidents"
    mock_llm.assert_called_once()


def test_assess_floor_one_uncovered():
    """
    An empty result makes the floor fail and gap_reason must name the exact
    symptom - that is what makes gap-directed looping chase the right gap.
    """
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]
    state["retrieved"] = {
        "API timeout": [{"id": "incident-a", "distance": 0.25}],
        "DB CPU spike": [],
    }

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API timeout matches incident-a"
        result = assess_node(state)

    assert result["sufficient"] is False
    assert "DB CPU spike" in result["gap_reason"]
    assert result["findings"] == "API timeout matches incident-a"


def test_assess_floor_missing_key():
    """A symptom absent from retrieved entirely is caught, not just []."""
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]
    state["retrieved"] = {"API timeout": [{"id": "incident-a", "distance": 0.25}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API timeout matches incident-a"
        result = assess_node(state)

    assert result["sufficient"] is False
    assert "DB CPU spike" in result["gap_reason"]


def test_assess_findings_strip_think():
    """Findings must not carry reasoning blocks into Diagnose."""
    state = create_state("API timeout")
    state["symptoms"] = ["API timeout"]
    state["retrieved"] = {"API timeout": [{"id": "incident-a", "distance": 0.25}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "<think>weighing it up</think>\nSymptom maps to incident-a"
        result = assess_node(state)

    assert result["findings"] == "Symptom maps to incident-a"


# ── Node 4: Diagnose ─────────────────────────────────────────────────────

def test_diagnose_parses_structure():
    """
    CAUSE | EVIDENCE | CONFIDENCE lines parse into dicts, confidence
    lowercased, order preserved.
    """
    state = create_state("API timeout and DB CPU spike")
    state["findings"] = "Symptoms converge on two distinct incidents"
    state["retrieved"] = {
        "API timeout": [{"id": "incident-a", "distance": 0.25}],
        "DB CPU spike": [{"id": "incident-b", "distance": 0.22}],
    }

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "Database config error | incident-a | HIGH\n"
            "Cache exhaustion | incident-b | Medium\n"
            "Network partition | incident-a, incident-b | low"
        )
        result = diagnose_node(state)

    assert len(result["diagnosis"]) == 3
    assert [d["confidence"] for d in result["diagnosis"]] == ["high", "medium", "low"]
    assert [d["cause"] for d in result["diagnosis"]] == [
        "Database config error",
        "Cache exhaustion",
        "Network partition",
    ]


def test_diagnose_drops_empty_evidence():
    """A line with no evidence cannot be grounded and is dropped."""
    state = create_state("Auth failure")
    state["findings"] = "One symptom, one match"
    state["retrieved"] = {"Auth failure": [{"id": "incident-c", "distance": 0.20}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "Credential rotation failure | incident-c | high\n"
            "Unknown cosmic ray failure | | low"
        )
        result = diagnose_node(state)

    assert len(result["diagnosis"]) == 1
    assert all(d["evidence"] for d in result["diagnosis"])
    assert result["diagnosis"][0] == {
        "cause": "Credential rotation failure",
        "evidence": "incident-c",
        "confidence": "high",
    }


def test_diagnose_drops_fabricated_ids():
    """
    Regression guard for the integration-run finding: qwen3 emits
    well-formed citations for incidents that were never retrieved.
    Syntactic grounding is not enough - cited IDs must intersect valid_ids.
    """
    state = create_state("Auth failure")
    state["findings"] = "One symptom, one match"
    state["retrieved"] = {"Auth failure": [{"id": "incident-c", "distance": 0.20}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "Credential rotation failure | incident-c | high\n"
            "Invented cause | INCIDENT_1 | high\n"
            "Another invented cause | incident-zzz | medium"
        )
        result = diagnose_node(state)

    assert len(result["diagnosis"]) == 1
    assert result["diagnosis"][0]["evidence"] == "incident-c"


def test_diagnose_skips_header_echo():
    """The model sometimes repeats the format instruction as a data row."""
    state = create_state("Auth failure")
    state["findings"] = "One match"
    state["retrieved"] = {"Auth failure": [{"id": "incident-c", "distance": 0.20}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "CAUSE | EVIDENCE | CONFIDENCE\n"
            "Credential rotation failure | incident-c | high"
        )
        result = diagnose_node(state)

    assert len(result["diagnosis"]) == 1
    assert result["diagnosis"][0]["cause"] == "Credential rotation failure"


def test_diagnose_no_evidence_skips_model():
    """
    With nothing retrieved there is nothing to ground against, so the model
    is never called. Asking it anyway is an invitation to hallucinate.
    """
    state = create_state("Something vague")
    state["findings"] = "No evidence found"
    state["retrieved"] = {"Something vague": []}

    with patch("src.agent.call_llm") as mock_llm:
        result = diagnose_node(state)

    assert result == {"diagnosis": []}
    mock_llm.assert_not_called()


# ── Routing ──────────────────────────────────────────────────────────────

def test_route_sufficient_goes_to_diagnose():
    state = create_state("x")
    state["sufficient"] = True
    state["iterations"] = 0
    assert route_after_assess(state) == "diagnose"


def test_route_capped_goes_to_diagnose():
    """The iteration cap overrides insufficiency - it is the stop guarantee."""
    state = create_state("x")
    state["sufficient"] = False
    state["iterations"] = MAX_ITERATIONS
    assert route_after_assess(state) == "diagnose"


def test_route_insufficient_under_cap_loops():
    state = create_state("x")
    state["sufficient"] = False
    state["iterations"] = 1
    assert route_after_assess(state) == "retrieve"

    