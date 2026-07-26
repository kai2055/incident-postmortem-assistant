"""
Shared fixtures and constants for all tests.
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from src.chunking import chunk_documents
from src.embedding import index_chunks
from src.ingestion import load_documents


@pytest.fixture(scope="session")
def corpus_path():
    return Path(__file__).parent.parent / "corpus" / "raw"

@pytest.fixture(scope="session")
def expected_chunks():
    return 107


@pytest.fixture(scope="session")
def temp_chroma():
    """
    Point vectorstore at a throwaway ChromaDB for the whole session.

    Session-scoped because embedding 82 chunks costs -100s on CPU, and a
    function-scoped fixture paid that cost once per test - eight times per 
    run. pytest.MonkeyPatch() is used instead of the monkeypatch fixture
    because that fixture is function-scoped and cannot be used here.
    """
    mp = pytest.MonkeyPatch()
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    mp.setattr("src.vectorstore.CHROMA_PATH", temp_path)
    yield temp_path
    mp.undo()
    shutil.rmtree(temp_dir)


@pytest.fixture(scope="session")
def indexed_chunks(temp_chroma, corpus_path, expected_chunks):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    index_chunks(chunks)
    return chunks


