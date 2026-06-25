"""Tests for the ingetsion module using the real corpus."""

import pytest
from pathlib import Path
from datetime import date

from src.ingestion import load_documents, Document


CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "raw"



def test_returns_exactly_all_documents():
    docs = load_documents(CORPUS_PATH)
    assert len(docs) == 15


def test_all_elements_are_document_instances():
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        assert isinstance(doc, Document)

def test_all_required_metadata_keys_present():
    required_keys = {
        "id", "title", "company", "date", "severity", 
        "duration_minutes", "affected_services", "root_cause_category"
    }
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        assert required_keys.issubset(doc.metadata.keys())


def test_metadata_values_not_empty():
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        for key, value in doc.metadata.items():
            if key == "affected_services":
                assert isinstance(value, list)
                assert len(value) > 0
                for service in value:
                    assert service != ""
                else:
                    assert value is not None
                    assert str(value).strip() != ""


def test_text_not_empty():
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        assert doc.text != ""
        assert doc.text.strip() != ""


def test_date_is_valid_iso_format():
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        date_obj = doc.metadata["date"]
        assert isinstance(date_obj, date)


def test_severity_is_allowed_value():
    allowed = {"critical", "major", "minor"}
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        severity = doc.metadata["severity"]
        assert severity in allowed, f"Invalid severity in {doc.metadata.get('id')}: {severity}"


def test_root_cause_category_is_allowed_value():
    allowed = {
        "configuration-error", "cascading-failure", "credential-auth",
        "network-bgp", "database-storage", "agent-ai", "supply-chain",
        "human-error", "other"
    }
    docs = load_documents(CORPUS_PATH)
    for doc in docs:
        category = doc.metadata["root_cause_category"]
        assert category in allowed, f"Invalid category in {doc.metadata.get('id')}: {category}"




