
from pathlib import Path

from src.chunking import Chunk, chunk_documents
from src.ingestion import load_documents

CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "raw"




def test_all_chunks_are_chunk_instances():
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        assert isinstance(chunk, Chunk)


def test_no_chunk_has_empty_text():
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        assert chunk.text != ""
        assert chunk.text.strip() != ""


def test_all_required_metadata_fields_present():
    required_keys = {
        "doc_id", "title", "company", "date", "severity",
        "root_cause_category", "section", "chunk_index", "total_chunks"
    }
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        assert required_keys.issubset(chunk.metadata.keys())


def test_section_header_appears_in_chunk_text():
    """Every chunk's text starts with its section header (##)"""
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        text = chunk.text.strip()
        assert text.startswith("##"), f"Chunk text does not start with header: {text[:50]}"


def test_long_section_split_correctly():
    """When a section is split into multiple chunks, each sub-chunk has the header"""
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)

    for chunk in chunks:
        if chunk.metadata["total_chunks"] > 1:
            text = chunk.text.strip()
            assert text.startswith('##'), f"Sub-chunk missing header: {text[:50]}"

def test_doc_id_matches_real_document():
    docs = load_documents(CORPUS_PATH)
    valid_ids = {doc.metadata["id"] for doc in docs}

    chunks = chunk_documents(docs)
    for chunk in chunks:
        assert chunk.metadata["doc_id"] in valid_ids, f"Invalid doc_id: {chunk.metadata['doc_id']}"
        


def test_total_chunks_matches_expected(corpus_path, expected_chunks):
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    assert len(chunks) == expected_chunks, f"Expected {expected_chunks}, got {len(chunks)}"

def test_section_is_allowed_value():
    """Section metadata is one of the allowed section names"""
    allowed = {"summary", "timeline", "root_cause", "resolution", "prevention", "impact"}
    docs = load_documents(CORPUS_PATH)
    chunks = chunk_documents(docs)
    for chunk in chunks:
        section = chunk.metadata["section"]
        assert section in allowed, f"Invalid section: {section}"

