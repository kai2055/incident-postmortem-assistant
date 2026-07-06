import pytest
from src.agent import build_diagnostic_graph, create_state


@pytest.mark.integration
def test_agent_end_to_end():
    """Real run: compile the graph, push a multi-symptom query through
    all four nodes with live Ollama. Proves composition, not diagnosis quality."""
    graph = build_diagnostic_graph()
    initial = create_state(
        "Our API started returning 503s, the database connection pool "
        "was exhausted, and checkout latency spiked."
    )
    final = graph.invoke(initial)

    # Structural assertions — the agent composed and produced output
    assert final["symptoms"], "decompose produced no symptoms"
    assert final["retrieved"], "retrieve produced no evidence"
    assert final["findings"], "assess produced no findings"
    assert isinstance(final["diagnosis"], list), "diagnose did not return a list"
    assert final["iterations"] >= 1, "iteration counter never advanced"

    # Visibility — see what the agent actually did
    print("\n\nSYMPTOMS:", final["symptoms"])
    print("ITERATIONS:", final["iterations"])
    print("SUFFICIENT:", final["sufficient"])
    print("FINDINGS:", final["findings"][:300])
    print("DIAGNOSIS:", final["diagnosis"])