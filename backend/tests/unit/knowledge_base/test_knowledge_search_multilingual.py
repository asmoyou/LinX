"""Tests for multilingual-aware retrieval heuristics and query expansion."""

import time

import pytest

from knowledge_base.knowledge_search import KnowledgeSearch, SearchFilter, SearchResult


@pytest.fixture(autouse=True)
def _reset_cross_language_shared_state():
    with KnowledgeSearch._cross_language_state_lock:
        KnowledgeSearch._cross_language_fail_until_by_key.clear()
        KnowledgeSearch._cross_language_failures_by_key.clear()
    yield
    with KnowledgeSearch._cross_language_state_lock:
        KnowledgeSearch._cross_language_fail_until_by_key.clear()
        KnowledgeSearch._cross_language_failures_by_key.clear()


def _build_search() -> KnowledgeSearch:
    """Construct lightweight KnowledgeSearch instance for internal method tests."""
    search = KnowledgeSearch.__new__(KnowledgeSearch)
    search.keyword_min_rank = 4.0
    search.hybrid_score_scale = 0.02
    search.cross_language_expansion_enabled = True
    search.cross_language_languages = ["en", "zh-CN"]
    search.cross_language_max_expansions = 2
    search.cross_language_max_queries = 3
    search.cross_language_provider = "test-provider"
    search.cross_language_model = ""
    search.cross_language_timeout_seconds = 2
    search.cross_language_failure_backoff_seconds = 10
    search._cross_language_fail_until = 0.0
    search._cross_language_cache = {}
    search._cross_language_state_key = "test-provider|<auto>|en,zh-CN"
    search.keyword_max_terms = 16
    return search


def test_vector_result_without_lexical_overlap_keeps_semantic_score():
    """Cross-lingual vector hits should not be over-penalized by lexical overlap."""
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-1",
        document_id="doc-1",
        content="A drifting kart takes a corner at high speed.",
        similarity_score=0.52,
        chunk_index=0,
        metadata={},
        search_method="vector",
    )

    reranked = search._rerank_by_query_overlap([result], ["漂移", "卡丁车"])

    assert len(reranked) == 1
    assert reranked[0].similarity_score >= 0.5
    assert reranked[0].metadata["query_overlap"] == 0.0
    assert reranked[0].metadata["semantic_floor_applied"] is True


def test_vector_result_with_overlap_uses_standard_blend():
    """When lexical overlap exists, normal overlap-aware blend should be used."""
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-2",
        document_id="doc-2",
        content="这段内容讨论了漂移卡丁车的入弯技巧。",
        similarity_score=0.52,
        chunk_index=0,
        metadata={},
        search_method="vector",
    )

    reranked = search._rerank_by_query_overlap([result], ["漂移", "卡丁车"])

    assert len(reranked) == 1
    assert reranked[0].similarity_score > 0.8
    assert reranked[0].metadata["query_overlap"] == 1.0
    assert reranked[0].metadata["semantic_floor_applied"] is False


def test_parse_cross_language_queries_supports_json_payload():
    """JSON response from expansion model should be parsed into query variants."""
    parsed = KnowledgeSearch._parse_cross_language_queries(
        '{"queries": ["drifting kart", "kart drifting technique"]}'
    )
    assert parsed == ["drifting kart", "kart drifting technique"]


def test_build_retrieval_queries_deduplicates_cross_language_variants(monkeypatch):
    """Expanded query variants should be deduplicated and capped."""
    search = _build_search()
    monkeypatch.setattr(
        search,
        "_expand_query_cross_language",
        lambda query: ["drifting kart", "漂移卡丁车", "drifting kart"],
    )

    queries = search._build_retrieval_queries("漂移卡丁车")

    assert queries == ["漂移卡丁车", "drifting kart"]


def test_bm25_search_merges_multi_query_results(monkeypatch):
    """BM25 should merge results from multiple query variants using best score per chunk."""
    search = _build_search()
    search_filter = SearchFilter(user_id="u1", top_k=2)

    def _fake_single(query: str, _filter: SearchFilter):
        if query == "漂移卡丁车":
            return [
                SearchResult(
                    chunk_id="c1",
                    document_id="d1",
                    content="zh chunk",
                    similarity_score=0.4,
                    chunk_index=0,
                    metadata={},
                    search_method="bm25",
                )
            ]
        return [
            SearchResult(
                chunk_id="c1",
                document_id="d1",
                content="en chunk",
                similarity_score=0.8,
                chunk_index=0,
                metadata={},
                search_method="bm25",
            ),
            SearchResult(
                chunk_id="c2",
                document_id="d2",
                content="en chunk 2",
                similarity_score=0.6,
                chunk_index=0,
                metadata={},
                search_method="bm25",
            ),
        ]

    monkeypatch.setattr(search, "_bm25_search_single", _fake_single)
    monkeypatch.setattr(
        search,
        "_keyword_fallback_search_multi",
        lambda **kwargs: [],
    )

    results = search._bm25_search(["漂移卡丁车", "drifting kart"], search_filter, query_terms=["漂移", "卡丁车"])

    assert [item.chunk_id for item in results[:2]] == ["c1", "c2"]
    assert results[0].similarity_score == 0.8


def test_cross_language_timeout_enters_shared_backoff(monkeypatch):
    """Timeout should trigger a long shared backoff that suppresses repeated calls."""
    search1 = _build_search()
    search2 = _build_search()

    monkeypatch.setattr(
        "knowledge_base.knowledge_search.resolve_provider",
        lambda _provider: {
            "protocol": "openai_compatible",
            "base_url": "http://example.com",
            "models": ["chat-model"],
        },
    )
    monkeypatch.setattr(
        search1,
        "_call_cross_language_model",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("Read timed out")),
    )

    first = search1._expand_query_cross_language("测试问题")
    remaining = search1._cross_language_fail_until - time.monotonic()

    assert first == []
    assert remaining >= 299

    called = {"count": 0}

    def _unexpected_call(**_kwargs):
        called["count"] += 1
        return '{"queries": ["test query"]}'

    monkeypatch.setattr(search2, "_call_cross_language_model", _unexpected_call)

    second = search2._expand_query_cross_language("另一个问题")

    assert second == []
    assert called["count"] == 0


def test_resolve_cross_language_model_falls_back_when_configured_model_is_stale():
    """Configured stale model should fallback to provider-available chat model."""
    search = _build_search()
    search.cross_language_provider = "vllm"
    search.cross_language_model = "Qwen3-Next-80B-A3B-Instruct-AWQ-4bit"

    resolved = search._resolve_cross_language_model(
        {"models": ["./Qwen3.5-35B-A3B-FP8", "bge-m3"]}
    )

    assert resolved == "./Qwen3.5-35B-A3B-FP8"


def test_resolve_cross_language_model_supports_normalized_match():
    """Configured model should match provider model with case/prefix normalization."""
    search = _build_search()
    search.cross_language_model = "Qwen3.5-35B-A3B-FP8"

    resolved = search._resolve_cross_language_model(
        {"models": ["./qwen3.5-35b-a3b-fp8", "bge-m3"]}
    )

    assert resolved == "./qwen3.5-35b-a3b-fp8"
