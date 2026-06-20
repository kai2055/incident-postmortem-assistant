
import pytest
import tempfile
import shutil
from pathlib import Path

from src.ingestion import load_documents
from src.chunking import chunk_documents
from src.embedding import (
    embed_text,
    embed_chunks,
    index_chunks,
    store_chunks,
    search_chunks,
    get_chroma_client,
    CHROMA_COLLECTION,
    VECTOR_DIM,
)

CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "raw"
EXPECTED_CHUNKS = 39

@pytest.fixture
def temp_Chroma(monkeypatch):
    """
    Point embedding at a throwaway ChromaDB for the whole test, then clean up
    """
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    monkeypatch.setattr("src.embedding.CHROMA_PATH", temp_path)
    yield temp_path
    shutil.rmtree(temp_dir)


@pytest.fixture
def indexed_chunks(temp_Chroma):
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    index_chunks(chunks)
    return chunks


def test_vector_dimension():
    vector = embed_text("test text", "search_document:")
    assert len(vector) == VECTOR_DIM
    assert all(isinstance(x, float) for x in vector)


def test_vector_count_matches_chunk_count():
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    chunks_with_vectors = embed_chunks(chunks)
    assert len(chunks_with_vectors) == EXPECTED_CHUNKS


def test_vector_contains_floats():
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    chunks_with_vectors = embed_chunks(chunks[:1])

    vector = chunks_with_vectors[0][1]
    assert all(isinstance(x, float) for x in vector)

def test_embedding_is_consistent():
    text = "This is a test sentence by Nikhil"
    vector1 = embed_text(text, "search_document:")
    vector2 = embed_text(text, "search_document:")

    assert len(vector1) == len(vector2)
    assert all(abs(a - b) < 0.0001 for a, b in zip(vector1, vector2))


def test_id_shape(temp_Chroma):
    """
    Every chunk id has the format doc_id:section:chunk_index.
    """
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    chunks_with_vectors = embed_chunks(chunks)

    store_chunks(chunks_with_vectors)

    client = get_chroma_client()
    collection = client.get_collection(CHROMA_COLLECTION)
    results = collection.get()

    for id_str in results["ids"]:
        parts = id_str.split(":")
        assert len(parts) == 3
        assert parts[2].isdigit()


def test_idempotency(temp_Chroma):
    """
    Indexing twice doesn't double the chunks
    """
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)

    # Index first time
    index_chunks(chunks)

    client = get_chroma_client()
    collection = client.get_collection(CHROMA_COLLECTION)
    count1 = collection.count()

    # Index second time (should upsert, not duplicate)
    index_chunks(chunks)

    collection = client.get_collection(CHROMA_COLLECTION)
    count2 = collection.count()

    assert count1 == count2 == EXPECTED_CHUNKS



def test_search_returns_expected_document(indexed_chunks):
    """
    Search for R2 outage returns the R2 incident as top result
    """
    results = search_chunks(
        "What caused the Cloudflare R2 outage?",
        top_k=3,
        collection_name=CHROMA_COLLECTION, 
    )

    assert len(results) > 0
    top_result = results[0]
    assert "cloudflare-r2-2025-03-21" in top_result["id"]