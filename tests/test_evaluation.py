
from unittest.mock import patch

from src.evaluation import (
    hit_at_k,
    reciprocal_rank,
    score_decline_query,
    score_retrieval_query,
    split_chunk_id,
)


def test_hit_at_k_found_at_first_position():
    assert hit_at_k(["a", "b", "c"], "a", k=5) is True

def test_hit_at_k_found_at_position_k():
    assert hit_at_k(["a", "b", "c"], "c", k=3) is True

def test_hit_at_k_just_past_k_is_miss():
    assert hit_at_k(["a", "b", "c","d"], "d", k=3) is False

def test_hit_at_k_is_miss():
    assert hit_at_k(["a", "b", "c"], "z", k=5) is False

def test_hit_at_k_list_shorter_than_k_does_not_crash():
    assert hit_at_k(["a"], "a", k=10) is True


def test_reciprocal_rank_first_position_is_one():
    assert reciprocal_rank(["a", "b", "c"], "a") == 1.0

def test_reciprocal_rank_second_position_is_half():
    assert reciprocal_rank(["a", "b", "c"], "b") == 0.5

def test_reciprocal_rank_third_position():
    assert abs(reciprocal_rank(["a", "b", "c"], "c") - (1 / 3)) < 1e-9

def test_reciprocal_rank_absent_is_zero():
    assert reciprocal_rank(["a", "b", "c"], "z") == 0.0

def test_reciprocal_rank_uses_first_occurence():
    assert reciprocal_rank(["a", "b", "c", "a"], "a") == 1.0


def test_split_chunk_id_normal():
    doc_id, section, = split_chunk_id("cloudflare-r2-2025-03-21:summary:0")
    assert doc_id == "cloudflare-r2-2025-03-21"
    assert section == "summary"

def test_split_chunk_id_doc_id_keeps_internal_hyphens():
    doc_id, _ = split_chunk_id("github-dns-2024-10-11:root_cause:2")
    assert doc_id == "github-dns-2024-10-11"

def test_split_chunk_id_no_colon_returns_none_section():
    doc_id, section = split_chunk_id("just-a-doc-id")
    assert doc_id == "just-a-doc-id"
    assert section is None


def test_score_retrieval_hit_at_rank_two():
    fake_result = [
        {"id": "wrong-doc:summary:0"},
        {"id": "cloudflare-r2-2025-03-21:root_cause:0"},
    ]

    query_entry = {
        "query": "anything - retrieve is mocked",
        "expected_doc_id": "cloudflare-r2-2025-03-21",
        "expected_section": "root_cause",
        "difficulty": "easy",
    }

    with patch("src.evaluation.retrieve", return_value=fake_result):
        scored = score_retrieval_query(query_entry, top_k=5, threshold=1.0)

    assert scored["hit"] is True
    assert scored["reciprocal_rank"] == 0.5
    assert scored["section_hit"] is True


def test_score_retrieval_query_miss_when_doc_absent():
    fake_results = [
        {"id": "wrong-doc-summary:0"},
        {"id": "other-wrong-doc:summary:0"},
    ]
    query_entry = {
        "query": "anything",
        "expected_doc_id": "cloudflare-r2-2025-03-21",
        "expected_section": "root_cause",
        "difficulty": "easy",
    }

    with patch("src.evaluation.retrieve", return_value=fake_results):
        scored = score_retrieval_query(query_entry, top_k=5, threshold=1.0)

    assert scored["hit"] is False
    assert scored["reciprocal_rank"] == 0.0



def test_score_decline_query_empty_means_declined():
    query_entry = {"query": "weather in Nepal", "difficulty": "no-match"}

    with patch("src.evaluation.retrieve", return_value=[]):
        scored = score_decline_query(query_entry, top_k=5, threshold=0.5)

    assert scored["declined"] is True


def test_score_decline_query_results_mean_leaked():
    query_entry = {"query": "weather in Nepal", "difficulty": "no-match"}
    fake_leak = [{"id": "some-unrelated-incident:summary:0"}]

    with patch("src.evaluation.retrieve", return_value=fake_leak):
        scored = score_decline_query(query_entry, top_k=5, threshold=1.0)

    assert scored["declined"] is False



