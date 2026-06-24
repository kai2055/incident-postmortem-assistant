
"""
Embedding module for the RAG pipeline.

Embeds text using nomic-embed-text via Ollama. Also contains
orchestrators (index_chunks, retrieve) that coordinate between
embedding and vectorstore layers
"""

from pathlib import Path
from typing import List, Tuple, Any

import ollama

from src.chunking import Chunk
from src.vectorstore import store_chunks, search, CHROMA_COLLECTION


# Configuration

EMBED_MODEL = "nomic-embed-text"
VECTOR_DIM = 768
RELEVANCE_THRESHOLD = 1.0 # loose placeholder; Layer 3 evaluation will tune this



# Embedding

def embed_text(text: str, prefix: str,) -> List[float]:
    """
    Embed a single text using Ollama with explicit prefix.

    Args:
        text: Text to embed
        prefix: Prefix to prepend to text (search_document: or search_query)

    Returns:
        List of floats (vector)
    
    """
    data = ollama.embeddings(
        model=EMBED_MODEL,
        prompt = f"{prefix}{text}",

    )
    return  data["embedding"]



def embed_chunks(chunks: List[Chunk]) -> List[Tuple[Chunk, List[float]]]:
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
        chunks: List[Chunk],
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
    top_k: int = 5,
    filter_metadata: dict = None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> List[dict]:
    """
    Retrieve relevant chunks for a query

    Steps: 
        1. Embed the query with "search_query:" prefix
        2. Search ChromaDB with the query vector
        3. Drop results whose distance is above the threshold (too far = irrelevant)


    Args:
        query: User question
        collection_name: Name of the ChromaDB collection
        top_k: Number of results to return
        filter_metadata: Optional filter (e.g, {"company": "Cloudflare})
        threshold: Max cosine distant to count as relevant. Smaller = stricter

    Returns:
        List of results within the threshold. May be empty if nothing is close enough.
    
    """
    query_vector = embed_text(query, "search_query:")
    results = search(query_vector, collection_name, top_k, filter_metadata)

    # Keep only results close enough to be relevant
    relevant = [ r for r in results if r["distance"] <= threshold]
    
    return relevant






# --- Main ---

def main():
    """Test the embedding module."""
    from src.ingestion import load_documents
    from src.chunking import chunk_documents

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
