"""Tests for the vectorstore module: ChromaDB storage and search"""

from src.ingestion import load_documents
from src.chunking import chunk_documents
from src.embedding import embed_chunks, embed_text, index_chunks
from src.vectorstore import store_chunks, search, get_chroma_client,to_chroma_where, CHROMA_COLLECTION


def test_store_and_search(temp_chroma, corpus_path):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)

    chunks_with_vectors = embed_chunks(chunks)
    store_chunks(chunks_with_vectors)

    query_vector = embed_text("Cloudflare R2 outage", "search_query:")
    results = search(query_vector, top_k=3)

    assert len(results) == 3
    assert results[0]["id"].startswith("cloudflare-r2-2025-03-21")


def test_search_with_filter(temp_chroma, corpus_path):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)

    chunks_with_vectors = embed_chunks(chunks)
    store_chunks(chunks_with_vectors)

    query_vector = embed_text("outage", "search_query:")
    results = search(query_vector, top_k=10, filter_metadata={"company": "Cloudflare"})

    assert len(results) > 0
    for result in results:
        assert result["metadata"]["company"] == "Cloudflare"



def test_idempotency(temp_chroma, corpus_path, expected_chunks):
    """
    Indexing twice doesn't duplicate chunks (stable ids + upsert)
    """
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)

    index_chunks(chunks)
    client = get_chroma_client()
    count1 = client.get_collection(CHROMA_COLLECTION).count()

    index_chunks(chunks)
    count2 = client.get_collection(CHROMA_COLLECTION).count()

    assert count1 == count2 == expected_chunks



def test_get_chroma_client_creates_directory(temp_chroma):
    client = get_chroma_client()
    assert client is not None
    assert temp_chroma.exists()


def test_index_chunks_creates_collection(indexed_chunks):
    client = get_chroma_client()
    names = [c.name for c in client.list_collections()]
    assert CHROMA_COLLECTION in names


def test_to_chroma_where_empty_returns_none():
    assert to_chroma_where({}) is None
    assert to_chroma_where(None) is None

def test_to_chroma_where_single_key_passes_through():
    assert to_chroma_where({"company": "Cloudflare"}) == {"company": "Cloudflare"}

def test_t0_chroma_where_multi_key_wraps_in_and():
    result = to_chroma_where(
        {"company": "Cloudflare", "root_cause_category": "configuration-error"}

    )
    assert "$and in result"
    assert {"company": "Cloudflare"} in result["$and"]
    assert {"root_cause_category": "configuration-error"} in result["$and"]
    assert len(result["$and"]) == 2
    
