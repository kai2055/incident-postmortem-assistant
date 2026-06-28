
"""
Vectorstore module for the RAG pipeline.

Handles all ChromaDB operations: client creation, storing vectors,
and searching vectors. This is a pure storage/retrieval layer with
no dependency on embeding or Ollama

"""
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import chromadb


# Config

CHROMA_PATH = Path("data/chromadb")
CHROMA_COLLECTION = "incidents"


# client

def get_chroma_client(persist_path: Optional[Path] = None) -> chromadb.PersistentClient:
    if persist_path is None:
        persist_path = CHROMA_PATH
    persist_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_path))


# Storage

def store_chunks(
    chunks_with_vectors: List[Tuple[Any, List[float]]],
    collection_name: str = CHROMA_COLLECTION,
) -> None:
    client = get_chroma_client()

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )

    ids = []
    texts = []
    vectors = []
    metadatas = []

    for chunk, vector in chunks_with_vectors:
        metadata = dict(chunk.metadata)

        # Convert date to string for ChromaDB
        if "date" in metadata:
            date_val = metadata["date"]
            if date_val is None:
                metadata["date"] = "unknown"
            elif isinstance(date_val, str):
                pass  # Already a string
            elif hasattr(date_val, 'isoformat'):
                metadata["date"] = date_val.isoformat()
            else:
                metadata["date"] = str(date_val)

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


def to_chroma_where(filters: dict) -> dict | None:
    if not filters:
        return None
    if len(filters) == 1:
        return filters
    return {"$and": [{k: v} for k, v in filters.items()]}


# Search

def search(
        query_vector: List[float],
        collection_name: str = CHROMA_COLLECTION,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Search ChromaDB using a pre-computed query vector.

    Args:
        query_vector: Pre-embedded query vector (list of floats)
        collection_name: Name of the ChromaDB collection
        top_k: Number od results to return
        filter_metadata: Optional filter (e.g, {"company: "cloudflare"})

    Returns:
        List of results with ids, documents, metadata, and distances.


    """
    client = get_chroma_client()
    collection = client.get_collection(collection_name)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=to_chroma_where(filter_metadata,)
    )

    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        }
        for i in range(len(results["ids"][0]))
    ]


# helper

def _build_chunk_id(chunk:Any) -> str:
    """Generate unique ID for a chunk using colon seperators."""
    doc_id = chunk.metadata.get("doc_id", "unknown")
    section = chunk.metadata.get("section", "unknown")
    index = chunk.metadata.get("chunk_index", 0)
    return f"{doc_id}:{section}:{index}"


# Main (testing)

def main():
    print("Vectorstore modeule loaded sucessfully")
    print(f"ChromaDB path: {CHROMA_PATH.absolute()}")
    print(f"Collection name: {CHROMA_COLLECTION}")

    client = get_chroma_client()
    collections = client.list_collections()
    print(f"Existing collections: {[c.name for c in collections]}")



if __name__ == "__main__":
    main()



    


