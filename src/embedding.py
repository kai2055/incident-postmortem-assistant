
"""
Embedding module for the RAG pipeline.

Embed chunks using nomic-embed-text via Ollama and stores them in ChromaDB for retrieval

"""

import os
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import chromadb
import ollama

from src.chunking import Chunk


# Configuration

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
VECTOR_DIM = 768
CHROMA_PATH = Path("data/chromadb")
CHROMA_COLLECTION = "incidents"


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


def _build_chunk_id(chunk: Chunk) -> str:
    """Generate unique ID for a chunk using colon seperator"""
    doc_id = chunk.metadata.get("doc_id", "unknown")
    section = chunk.metadata.get("section", "unknown")
    index = chunk.metadata.get("chunk_index", 0)
    return f"{doc_id}:{section}:{index}"


# Storage



def get_chroma_client(persist_path: Optional[Path] = None) -> chromadb.PersistentClient:
    """Get or create ChromaDB client"""
    if persist_path is None:
        persist_path = CHROMA_PATH
    persist_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_path))


def store_chunks(
        chunks_with_vectors: List[Tuple[Chunk, List[float]]],
        collection_name: str = CHROMA_COLLECTION,
) -> None:
    """
    Store embedded chunks in ChromaDB using upsert

    Args:
        chunks_with_vectors: List of (chunk, vector) pairs.
        collection_name: Name of the ChromaDB collection


    """

    client = get_chroma_client()

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = []
    texts = []
    vectors = []
    metadatas = []

    for chunk, vector in chunks_with_vectors:
        metadata = dict(chunk.metadata)

        # Convert date to string for ChromaDB
        if "date" in metadata and not isinstance(metadata["date"], str):
            metadata["date"] = metadata["date"].isoformat()


        ids.append(_build_chunk_id(chunk))
        texts.append(chunk.text)
        vectors.append(vector)
        metadatas.append(metadata)

    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=vectors,
        metadatas=metadatas,
    )



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


# --- Search (for testing only) ---

def search_chunks(
    query: str,
    collection_name: str = CHROMA_COLLECTION,
    top_k: int = 5,
    filter_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Search ChromaDB for chunks matching the query.

    Args:
        query: User question.
        collection_name: Name of the ChromaDB collection.
        top_k: Number of results to return.
        filter_metadata: Optional filter (e.g., {"company": "Cloudflare"}).

    Returns:
        List of results with ids, documents, metadatas, and distances.
    """
    client = get_chroma_client()
    collection = client.get_collection(collection_name)

    query_vector = embed_text(query, "search_query:")

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=filter_metadata,
    )

    # Reformat results
    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        }
        for i in range(len(results["ids"][0]))
    ]


# --- Main ---

def main():
    """Test the embedding module."""
    from pathlib import Path
    from .ingestion import load_documents
    from .chunking import chunk_documents

    corpus_path = Path("corpus/raw")
    print(f"Loading documents from: {corpus_path.absolute()}")
    docs = load_documents(corpus_path)
    print(f"Loaded {len(docs)} documents.")

    print("Chunking...")
    chunks = chunk_documents(docs)
    print(f"Generated {len(chunks)} chunks.")

    print("Indexing...")
    index_chunks(chunks)

    print("Testing search...")
    results = search_chunks("What caused the Cloudflare R2 outage?", top_k=3)
    for result in results:
        print(f"  [{result['id']}] distance={result['distance']:.4f}")
        print(f"      {result['text'][:100].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
