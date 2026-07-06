from unittest.mock import patch

from src.agent import decompose_node, create_state, retrieve_node, assess_node, diagnose_node, route_after_assess, MAX_ITERATIONS



def test_decompose_node_clean_response():
    """
    Clean LLM response is parsed into a list of symptoms
    """
    state = create_state("Our API is timing out and the database CPU is spiking.")

    with patch ("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API is timing out\ndatabase CPU is spiking"

        result = decompose_node(state)

    assert result == {"symptoms": ["API is timing out", "database CPU is spiking"]}
    mock_llm.assert_called_once()


def test_decompose_node_strips_think_tokens():
    """
    <think> blocks are stripped before parsing; only real symptoms remain
    """
    state = create_state("Users cannot log in and payments are failing.")
    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = (
            "<think>\n"
            "Let me extract the symptoms from this description.\n"
            "The engineer mentions login issues and payment failures.\n"
            "</think>\n"
            "Users cannot log in\n"
            "payments are failing"
        )
        result = decompose_node(state)
    assert result == {"symptoms":["Users cannot log in", "payments are failing"] }
    mock_llm.assert_called_once()




def test_retrieve_node_normal():
    """
    Two symptomss -> retrieve called per symptom, results keyed correctly 
    """
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]

    with patch("src.agent.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = [
            [{"id": "incident-a", "distance":0.25}],
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
    mock_retrieve.assert_any_call("API timeout", top_k=3)
    mock_retrieve.assert_any_call("DB CPU spike", top_k=3)



def test_retrieve_node_preserves_empty():
    """
    A symptom with no matches -> key exists with [], not dropped
    """
    state = create_state("DDos attack on CDN")
    state["symptoms"] = ["DDos attack", "CDN latency"]

    with patch("src.agent.retrieve") as mock_retrieve:
        mock_retrieve.side_effect = [
            [], # no matches for DDos attack - threshold filtered everything
            [{"id": "incident-c", "distance": 0.20}],
        ]
        
        result = retrieve_node(state)

    assert result["retrieved"]["DDos attack"] == []
    assert result["retrieved"]["CDN latency"] == [{"id": "incident-c", "distance":0.20}]


def test_retrieve_node_empty_symptoms():
    """
    No symptoms -> empty retrieved, no crash
    """
    state = create_state("nothing specific")
    state["symptoms"] = []

    with patch("src.agent.retrieve") as mock_retrieve:
        result = retrieve_node(state)

    assert result == {"retrieved": {}, "iterations": 1}
    mock_retrieve.assert_not_called()



def test_assess_floor_all_covered():
    """
    Every symptom has retrieved evidence -> sufficient = True, no gap findings passed through
    """
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
    One symptom returns [] -> sufficient=False, gap_reason names it, findings still produced
    """
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]
    state["retrieved"] = {
        "API timeout": [{"id":"incident-a", "distance": 0.25}],
        "DB CPU spike": [], # threshold filtered everything
    }

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API timeout matches incident-a"

        result = assess_node(state)

    assert result["sufficient"] is False
    assert "DB CPU spike" in result["gap_reason"]
    assert result["findings"] == "API timeout matches incident-a"
    mock_llm.assert_called_once()



def test_assess_floor_missing_key():
    """
    Symptom key absent from retrieved entirely -> still caught by .get() default
    """
    state = create_state("API timeout and DB CPU spike")
    state["symptoms"] = ["API timeout", "DB CPU spike"]
    # "DB CPU spike is completely missing - not just []"
    state["retrieved"] = {"API timeout": [{"id": "incident-a", "distance":0.25}]}

    with patch("src.agent.call_llm") as mock_llm:
        mock_llm.return_value = "API timeout matches incident-a"

        result = assess_node(state)

    assert result["sufficient"] is False
    assert "DB CPU spike" in result["gap_reason"]
    assert result["findings"] == "API timeout matches incident-a"
    mock_llm.assert_called_once()
    


def test_diagnose_parse_structure():
    """
    Clean CAUSE | EVIDENCE | CONFIDENCE lines parse into structure dicts,
    confidence lowercased, order preserved.
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

    for item in result["diagnosis"]:
        assert "cause" in item
        assert "evidence" in item
        assert "confidence" in item

    assert result["diagnosis"][0]["confidence"] == "high"
    assert result["diagnosis"][1]["confidence"] == "medium"
    assert result["diagnosis"][2]["confidence"] == "low"

    assert result["diagnosis"][0]["cause"] == "Database config error"
    assert result["diagnosis"][1]["cause"] == "Cache exhaustion"
    assert result["diagnosis"][2]["cause"] == "Network partition"

    mock_llm.assert_called_once()




def test_diagnose_grounding_filter_drops_ungrounded():
    """
    A line with empty evidence is filtered out; only grounded candidates survive
    """
    state = create_state("Auth failure")
    state["findings"] = "One symptom, one match"
    state["retrieved"] = {
        "Auth failure": [{"id": "incident-c", "distance": 0.20}],
    }

    with patch("src.agent.call_llm") as mock_llm:
        # Two lines fed in, one grounded, one ungrounded (empty evidence)
        mock_llm.return_value = (
            "Credential rotation failure | incident-c | high\n"
            "Unknown cosmic ray failure | | low"
        )

        result = diagnose_node(state)

    # Count dropped by one - proves the filter removed it
    assert len(result["diagnosis"]) == 1

    # Mechanical grounding check: nothing ungrounded survives
    assert all(d["evidence"] for d in result["diagnosis"])

    #The grounded one is preserved correctly
    assert result["diagnosis"][0] == {
        "cause": "Credential rotation failure",
        "evidence": "incident-c",
        "confidence": "high",
    }

    mock_llm.assert_called_once()




def test_route_sufficient():
    """
    Sufficient=True -> diagnose regardless of iteration count.
    """
    state = create_state("x")
    state["sufficient"] = True
    state["iterations"] = 0
    assert route_after_assess(state) == "diagnose"


def test_route_capped():
    """Iterations at cap -> dignose even if not sufficient"""
    state = create_state("x")
    state["sufficient"] = False
    state["iterations"] = MAX_ITERATIONS
    assert route_after_assess(state) == "diagnose"

def test_route_uncapped_insufficiently():
    """
    Not sufficient and under cap -> loop back to retrieve
    """
    state = create_state("x")
    state["sufficient"] = False
    state["iterations"] = 1
    assert route_after_assess(state) == "retrieve"






