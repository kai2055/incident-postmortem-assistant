
"""
Embedding module for the RAG pipeline.

Embeds text using nomic-embed-text via Ollama. Also contains
orchestrators (index_chunks, retrieve) that coordinate between
embedding and vectorstore layers
"""

from pathlib import Path

import ollama
import os

from src.chunking import Chunk
from src.vectorstore import CHROMA_COLLECTION, search, store_chunks
from dotenv import load_dotenv
load_dotenv()

# Configuration

EMBED_MODEL = "nomic-embed-text"
VECTOR_DIM = 768
RELEVANCE_THRESHOLD = 0.30
DEFAULT_TOP_K = 10
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "ollama")
GEMINI_EMBED_MODEL = "gemini-embedding-001"



# Embedding

def embed_text(text: str, prefix: str) -> list[float]:
    """
    Embed a single text. Provider chosen by EMBED_PROVIDER env var:
        ollama  - local inference, nomic-embed-text (default, dev path)
        gemini  - hosted inference, gemini-embedding-001 (deploy path)

    Both produce 768-dim vectors. NOTE: they are DIFFERENT models, so the
    vector store must be built with the same provider that queries it.
    """
    if EMBED_PROVIDER == "gemini":
        return _embed_gemini(text, prefix)
    return _embed_ollama(text, prefix)


def _embed_ollama(text: str, prefix: str) -> list[float]:
    data = ollama.embeddings(model=EMBED_MODEL, prompt=f"{prefix}{text}")
    return data["embedding"]


def _embed_gemini(text: str, prefix: str) -> list[float]:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "EMBED_PROVIDER=gemini but GEMINI_API_KEY is not set. Add it to .env"
        )

    client = genai.Client(api_key=api_key)
    # Map your prefix convention to Gemini's task_type.
    task_type = "RETRIEVAL_QUERY" if prefix.startswith("search_query") else "RETRIEVAL_DOCUMENT"

    result = client.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=768,
        ),
    )
    return result.embeddings[0].values



def embed_chunks(chunks: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
    """
    Embed a list of chunks.

    Args:
        chunks: List of Chunk objects

    Returns:
        List of (chunk, vector) pairs.
    
    """

    results = []
    for chunk in chunks:
        vector = embed_text(chunk.text, "search_document:")
        results.append((chunk, vector))
    return results








# Orchestrator

def index_chunks(
        chunks: list[Chunk],
        collection_name: str = CHROMA_COLLECTION,
) -> None:
    """
    Full indexing pipeline: embed chunks and store in ChromaDB.

    Args:
        chunks: List od Chunk objects.
        collection_name: Name of the ChromeDB collection
    
    
    """

    chunks_with_vectors = embed_chunks(chunks)
    store_chunks(chunks_with_vectors, collection_name)



def retrieve(
    query: str,
    collection_name: str = CHROMA_COLLECTION,
    top_k: int = DEFAULT_TOP_K,
    filter_metadata: dict | None = None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> list[dict]:
    """
    Retrieve relevant chunks for a query

    Steps: 
        1. Embed the query with "search_query:" prefix
        2. Search ChromaDB with the query vector
        3. If threshold is not None, drop results whose distance is above it


    Args:
        query: User question
        collection_name: Name of the ChromaDB collection
        top_k: Number of results to return
        filter_metadata: Optional filter (e.g, {"company": "Cloudflare})
        threshold: Max cosine distant to count as relevant. 
                None means "no distance cutoff - return all metadata-matched
                results ranked. 
                Smaller = stricter

    Returns:
        List of results within the threshold, or all results if threshold is None
          May be empty if nothing is close enough (when threshold is set)
    
    """
    query_vector = embed_text(query, "search_query:")
    results = search(query_vector, collection_name, top_k, filter_metadata)

    # If threshold is None, skip distance filtering - return all metadata-matched results
    if threshold is None:
        return results


    # Keep only results close enough to be relevant
    relevant = [ r for r in results if r["distance"] <= threshold]
    
    return relevant






# --- Main ---

def main():
    """Test the embedding module."""
    from src.chunking import chunk_documents
    from src.ingestion import load_documents

    corpus_path = Path("corpus/raw")
    print(f"Loading documents from: {corpus_path.absolute()}")
    docs = load_documents(corpus_path)
    print(f"Loaded {len(docs)} documents.")

    print("Chunking...")
    chunks = chunk_documents(docs)
    print(f"Generated {len(chunks)} chunks.")

    print("Indexing...")
    index_chunks(chunks)

    print("Testing retrieval")
    results = retrieve("What caused the Cloudflare R2 outage?", top_k=3)
    
    for result in results:
        print(f"  [{result['id']}] distance={result['distance']:.4f}")
        print(f"      {result['text'][:100].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
