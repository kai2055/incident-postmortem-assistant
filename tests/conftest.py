"""
Shared fixtures and constants for all tests.
"""
import pytest
import tempfile
import shutil
from pathlib import Path

from src.ingestion import load_documents
from src.chunking import chunk_documents
from src.embedding import index_chunks


@pytest.fixture
def corpus_path():
    return Path(__file__).parent.parent / "corpus" / "raw"

@pytest.fixture
def expected_chunks():
    return 68



@pytest.fixture
def temp_chroma(monkeypatch):
    """
    Point vectorsstore at a throwaway ChromaDB for the whole test,
    then clean up
    """
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    monkeypatch.setattr("src.vectorstore.CHROMA_PATH", temp_path)
    yield temp_path
    shutil.rmtree(temp_dir)


@pytest.fixture
def indexed_chunks(temp_chroma, corpus_path, expected_chunks):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    index_chunks(chunks)
    return chunks
