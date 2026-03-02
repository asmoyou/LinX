"""Unit tests for keyword retrieval semantics in MemoryRepository."""

from memory_system.memory_repository import MemoryRepository


def test_term_matches_content_respects_latin_boundaries():
    content = MemoryRepository._normalize_keyword_text("The online platform is stable.")

    assert MemoryRepository._term_matches_content(content, "platform")
    assert not MemoryRepository._term_matches_content(content, "line")


def test_term_matches_content_supports_cjk_substring():
    content = MemoryRepository._normalize_keyword_text("灵枢平台由小白客开发")

    assert MemoryRepository._term_matches_content(content, "灵枢")
    assert MemoryRepository._term_matches_content(content, "开发")


def test_compute_keyword_match_features_includes_phrase_and_coverage():
    features = MemoryRepository._compute_keyword_match_features(
        content="LinX平台由小白客开发，中文名是灵枢平台。",
        query_terms=["linx", "开发", "灵枢平台"],
        normalized_full_query=MemoryRepository._normalize_keyword_text("linx 开发"),
    )

    assert features["strict_term_hits"] >= 2
    assert features["strong_term_hits"] >= 2
    assert 0.6 <= float(features["coverage_ratio"]) <= 1.0
    assert features["phrase_hit"] is False


def test_keyword_quality_gate_rejects_multi_term_without_strong_match():
    keep = MemoryRepository._passes_keyword_quality_gate(
        strict_term_hits=3,
        strong_term_hits=0,
        phrase_hit=False,
        required_term_hits=2,
        total_terms=4,
    )

    assert keep is False
