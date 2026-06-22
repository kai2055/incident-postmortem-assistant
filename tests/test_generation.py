from unittest.mock import patch
from src.generation import(
    _prettify_section,
    _build_sources,
    generate_answer,
    answer_query,
)



def test_prettify_section():
    assert _prettify_section("root_cause") == "Root Cause"
    assert _prettify_section("summary") == "Summary"
    assert _prettify_section("timeline") == "Timeline"
    assert _prettify_section("resolution") == "Resolution"
    assert _prettify_section("prevention") == "Prevention"


def test_build_sources_numbering():
    fake_results = [
        {"text": "chunk one", "metadata":{"company": "A", "date": "2025-01-01","section": "summary"}},
        {"text": "chunk two", "metadata":{"company": "B", "date": "2025-02-02","section": "root_cause"}},
    ]

    context, sources = _build_sources(fake_results)

    assert "[1]" in context
    assert "[2]" in context
    assert len(sources) == 2


def test_build_sources_label_format():
    fake_result = [
        {"text": "some text", "metadata":{"company": "Cloudflare", "date": "2025-03-03","section": "root_cause"}},
    ]
    context, sources = _build_sources(fake_result)

    expected_label = "Cloudflare (2025-03-03) - Root Cause"
    assert expected_label in context
    assert sources[0]["company"] == "Cloudflare"
    assert sources[0]["date"] == "2025-03-03"
    assert sources[0]["section"] == "Root Cause"


def test_generate_answer_shape():
    fake_results = [
        {"text": "test chunk", "metadata": {"company": "Cloudflare", "date": "2025-03-21", "section": "summary"}},
    ]

    with patch("src.generation.ollama.generate") as mock_ollama:
        mock_ollama.return_value = {"response": "The answer is [1]."}
        result = generate_answer("What happened", fake_results)

    assert "answer" in result
    assert "sources" in result
    assert result["answer"] == "The answer is [1]."
    assert len(result["sources"]) == 1
    assert result["sources"][0]["company"] == "Cloudflare"
    assert result["sources"][0]["section"] == "Summary"


def test_generate_answer_citation_preserved():
    """If the model write a citation, it stays in the answer"""
    fake_results = [
        {"text": "chunk", "metadata": {"company": "A", "date": "2025-01-01", "section": "summary"}},
    ]

    with patch("src.generation.ollama.generate") as mock_ollama:
        mock_ollama.return_value = {"response": "Caused by error [1]."}
        result = generate_answer("What caused it?", fake_results)

    assert "[1]" in result["answer"]


def test_answer_query_shape():
    with patch("src.generation.retrieve") as mock_retrieve, \
        patch("src.generation.generate_answer") as mock_gen:

        mock_retrieve.return_value = [
            {"text": "t", "metadata": {"company": "C", "date": "2025-01-01","section": "summary"}}
        ]
        mock_gen.return_value = {
            "answer": "Test answer [1].",
            "sources": [{"number": 1, "company": "C", "date": "2025-01-01", "section": "Summary", "id": "test" }],
        }

        result = answer_query("test question", top_k=1)

    assert "answer" in result
    assert "sources" in result
    assert isinstance(result["sources"], list)
    mock_retrieve.assert_called_once()
