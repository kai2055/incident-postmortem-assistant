
from unittest.mock import patch

import pytest

from src.chunking import chunk_documents
from src.embedding import embed_chunks, embed_text, retrieve
from src.ingestion import load_documents


@pytest.mark.slow
def test_vector_dimension():
    vector = embed_text("test text", "search_document:")
    assert len(vector) == 768
    assert all(isinstance(x, float) for x in vector)

@pytest.mark.slow
def test_vector_count_matches_chunk_count(corpus_path):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    sample = chunks[:5]
    chunks_with_vectors = embed_chunks(sample)
    assert len(chunks_with_vectors) == len(sample)

@pytest.mark.slow
def test_vector_contains_floats(corpus_path):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    chunks_with_vectors = embed_chunks(chunks[:1])
    vector = chunks_with_vectors[0][1]
    assert all(isinstance(x, float) for x in vector)

    
@pytest.mark.slow
def test_embedding_is_consistent():
    text = "This is a test sentence by Nikhil"
    vector1 = embed_text(text, "search_document:")
    vector2 = embed_text(text, "search_document:")

    assert len(vector1) == len(vector2)
    assert all(abs(a - b) < 0.0001 for a, b in zip(vector1, vector2))


@pytest.mark.slow
def test_retrieve_returns_expected_document(indexed_chunks):
    results = retrieve("What caused the Cloudflare R2 outage?", top_k=3)
    assert len(results) > 0
    assert "cloudflare-r2-2025-03-21" in results[0]["id"]

@pytest.mark.slow
def test_retrieve_with_filter(indexed_chunks):
    """
    retrieve() with a metadata filter returns only matching documents.
    """
    results = retrieve(
        "outage",
        top_k=5,
        filter_metadata={"company": "Cloudflare"},

    )
    assert len(results) > 0
    for result in results:
        assert result["metadata"]["company"] == "Cloudflare"


@pytest.mark.slow
def test_retrieve_returns_cosine_distance(indexed_chunks):
    results = retrieve("What caused the Cloudflare R2 outage?", top_k=3)
    for result in results:
        assert "distance" in result
        assert 0 <= result["distance"] <= 2


def test_retrieve_filters_by_threshold():
    with patch("src.embedding.embed_text") as mock_embed, \
         patch("src.embedding.search") as mock_search:
        
        mock_embed.return_value = [0.0] * 768
        mock_search.return_value = [
            {"id": "a", "text": "close", "metadata": {}, "distance": 0.2},
            {"id": "b", "text": "far", "metadata": {}, "distance": 1.5},
        ]

        results = retrieve("query", threshold=1.0)

    assert len(results) == 1
    assert results[0]["id"] == "a"
        
