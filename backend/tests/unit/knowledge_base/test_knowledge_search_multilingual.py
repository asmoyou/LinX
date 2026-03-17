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
    search.rerank_top_k = 30
    search.rerank_doc_max_chars = 1600
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


def test_build_retrieval_queries_skips_cross_language_expansion_for_short_query(monkeypatch):
    """Very short keyword queries should not invoke cross-language expansion."""
    search = _build_search()
    called = {"count": 0}

    def _unexpected_expand(_query: str):
        called["count"] += 1
        return ["gunpowder"]

    monkeypatch.setattr(search, "_expand_query_cross_language", _unexpected_expand)

    queries = search._build_retrieval_queries("火药")

    assert queries == ["火药"]
    assert called["count"] == 0


def test_parse_cross_language_queries_filters_placeholder_variants():
    """Placeholder outputs like ellipsis should not become retrieval query variants."""
    parsed = KnowledgeSearch._parse_cross_language_queries(
        '{"queries": ["...", "火药", "gunpowder"]}'
    )
    assert parsed == ["火药", "gunpowder"]


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

    results = search._bm25_search(
        ["漂移卡丁车", "drifting kart"], search_filter, query_terms=["漂移", "卡丁车"]
    )

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

    resolved = search._resolve_cross_language_model({"models": ["./Qwen3.5-35B-A3B-FP8", "bge-m3"]})

    assert resolved == "./Qwen3.5-35B-A3B-FP8"


def test_resolve_cross_language_model_supports_normalized_match():
    """Configured model should match provider model with case/prefix normalization."""
    search = _build_search()
    search.cross_language_model = "Qwen3.5-35B-A3B-FP8"

    resolved = search._resolve_cross_language_model({"models": ["./qwen3.5-35b-a3b-fp8", "bge-m3"]})

    assert resolved == "./qwen3.5-35b-a3b-fp8"


def test_parse_rerank_response_normalizes_negative_scores() -> None:
    search = _build_search()

    parsed = search._parse_rerank_response(
        {
            "results": [
                {"index": 0, "relevance_score": -8.3},
                {"index": 1, "relevance_score": -1.2},
                {"index": 2, "relevance_score": -4.0},
            ]
        },
        3,
    )

    assert [index for index, _ in parsed] == [1, 2, 0]
    assert parsed[0][1] == 1.0
    assert 0.0 < parsed[1][1] < 1.0
    assert parsed[-1][1] == 0.0


def test_rerank_blend_uses_base_score_instead_of_rank_prior(monkeypatch) -> None:
    search = _build_search()
    search.rerank_enabled = True
    search.rerank_provider = "provider-a"
    search.rerank_model = "reranker-a"
    search.rerank_weight = 0.85

    result = SearchResult(
        chunk_id="chunk-1",
        document_id="doc-1",
        content="完全不相关的内容",
        similarity_score=0.42,
        chunk_index=0,
        metadata={},
        search_method="vector",
    )

    monkeypatch.setattr(
        "knowledge_base.knowledge_search.resolve_provider",
        lambda _provider: {"base_url": "http://example.com", "api_key": None},
    )
    sibling = SearchResult(
        chunk_id="chunk-2",
        document_id="doc-2",
        content="另一段无关内容",
        similarity_score=0.4,
        chunk_index=1,
        metadata={},
        search_method="vector",
    )
    monkeypatch.setattr(search, "_call_rerank_api", lambda **_kwargs: [(0, 0.05), (1, 0.01)])

    reranked, applied = search._rerank_with_model("火药", [result, sibling], top_k=10)

    assert applied is True
    assert reranked[0].similarity_score < 0.11
    assert reranked[0].metadata["base_score"] == 0.42


def test_effective_min_relevance_score_keeps_system_floor_when_rerank_is_unavailable() -> None:
    search = _build_search()
    search.min_relevance_score = 0.3

    assert (
        search._resolve_effective_min_relevance_score(
            0.01,
            model_rerank_applied=False,
        )
        == 0.3
    )
    assert (
        search._resolve_effective_min_relevance_score(
            0.01,
            model_rerank_applied=True,
        )
        == 0.01
    )


def test_rerank_uses_configured_candidate_pool_limit(monkeypatch) -> None:
    search = _build_search()
    search.rerank_enabled = True
    search.rerank_provider = "provider-a"
    search.rerank_model = "reranker-a"
    search.rerank_weight = 0.5
    search.rerank_top_k = 12

    results = [
        SearchResult(
            chunk_id=f"chunk-{idx}",
            document_id=f"doc-{idx}",
            content=f"content-{idx}",
            similarity_score=0.6 - idx * 0.01,
            chunk_index=idx,
            metadata={},
            search_method="vector",
        )
        for idx in range(15)
    ]

    monkeypatch.setattr(
        "knowledge_base.knowledge_search.resolve_provider",
        lambda _provider: {"base_url": "http://example.com", "api_key": None},
    )

    called = {"documents": 0}

    def _fake_call(**kwargs):
        called["documents"] = len(kwargs["documents"])
        return [(0, 0.9), (1, 0.8), (2, 0.7)]

    monkeypatch.setattr(search, "_call_rerank_api", _fake_call)

    reranked, applied = search._rerank_with_model("query", results, top_k=1)

    assert applied is True
    assert called["documents"] == 12
    assert len(reranked) == 15


def test_short_literal_query_without_lexical_support_is_filtered() -> None:
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-1",
        document_id="doc-1",
        content="完全不相关的内容",
        similarity_score=0.41,
        chunk_index=0,
        metadata={"rerank_score": 0.08},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="火药",
        query_terms=["火药"],
        bm25_results=[],
        results=[result],
    )

    assert guarded == []


def test_short_literal_query_keeps_exact_match_without_bm25() -> None:
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-2",
        document_id="doc-2",
        content="火药的配方和历史发展",
        similarity_score=0.38,
        chunk_index=0,
        metadata={"rerank_score": 0.12},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="火药",
        query_terms=["火药"],
        bm25_results=[],
        results=[result],
    )

    assert guarded == [result]


def test_short_compound_query_with_rerank_signal_keeps_supported_candidate() -> None:
    search = _build_search()
    relevant = SearchResult(
        chunk_id="chunk-kart",
        document_id="doc-kart",
        content="视频片段为开场镜头，呈现卡丁车赛道的动态场景。",
        similarity_score=0.12,
        chunk_index=0,
        metadata={"rerank_score": 0.05, "base_score": 0.5074},
        search_method="vector",
    )
    irrelevant = SearchResult(
        chunk_id="chunk-noise",
        document_id="doc-noise",
        content="完全不相关的监控平台介绍。",
        similarity_score=0.07,
        chunk_index=1,
        metadata={"rerank_score": 0.01, "base_score": 0.45},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="小赛车",
        query_terms=["小赛车", "小赛", "赛车"],
        bm25_results=[],
        results=[relevant, irrelevant],
    )

    assert guarded == [relevant]
    assert guarded[0].similarity_score >= 0.45


def test_short_compound_query_without_rerank_signal_is_filtered() -> None:
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-icecream",
        document_id="doc-icecream",
        content="完全不相关的内容",
        similarity_score=0.06,
        chunk_index=0,
        metadata={"rerank_score": 0.0012, "base_score": 0.45},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="冰淇淋",
        query_terms=["冰淇淋", "冰淇", "淇淋"],
        bm25_results=[],
        results=[result],
    )

    assert guarded == []


def test_short_compound_query_with_weak_positive_rerank_signal_is_still_filtered() -> None:
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-icecream-weak",
        document_id="doc-icecream-weak",
        content="完全不相关的内容",
        similarity_score=0.08,
        chunk_index=0,
        metadata={"rerank_score": 0.0144, "base_score": 0.45},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="冰淇淋",
        query_terms=["冰淇淋", "冰淇", "淇淋"],
        bm25_results=[],
        results=[result],
    )

    assert guarded == []


def test_short_compound_query_can_fallback_to_clear_vector_leader() -> None:
    search = _build_search()
    leader = SearchResult(
        chunk_id="chunk-kart",
        document_id="doc-kart",
        content="视频片段为开场镜头，呈现卡丁车赛道的动态场景。",
        similarity_score=0.0,
        chunk_index=0,
        metadata={"base_score": 0.5074},
        search_method="vector",
    )
    runner_up = SearchResult(
        chunk_id="chunk-noise",
        document_id="doc-noise",
        content="完全不相关的监控平台介绍。",
        similarity_score=0.0,
        chunk_index=1,
        metadata={"base_score": 0.4649},
        search_method="vector",
    )

    guarded = search._apply_short_query_precision_guard(
        query="小赛车",
        query_terms=["小赛车", "小赛", "赛车"],
        bm25_results=[],
        results=[leader, runner_up],
    )

    assert guarded == [leader]
    assert guarded[0].similarity_score >= 0.45


def test_sanitize_rerank_text_normalizes_multimodal_scaffolding() -> None:
    cleaned = KnowledgeSearch._sanitize_rerank_text(
        "Audio Transcript:\n<|nospeech|>欢迎来到卡丁车赛道。\n\n"
        "Visual Analysis:\nVideo Summary:\n### 摘要\n"
        "**1) 整体剧情** 卡丁车高速过弯。"
    )

    assert "<|" not in cleaned
    assert "Audio Transcript:" not in cleaned
    assert "Video Summary:" not in cleaned
    assert "卡丁车赛道" in cleaned
    assert "卡丁车高速过弯" in cleaned


def test_vector_result_without_overlap_does_not_apply_semantic_floor_for_single_term_query():
    """Single-term exact queries should not inflate unrelated vector hits via semantic floor."""
    search = _build_search()
    result = SearchResult(
        chunk_id="chunk-short",
        document_id="doc-short",
        content="Completely unrelated content.",
        similarity_score=0.44,
        chunk_index=0,
        metadata={},
        search_method="vector",
    )

    reranked = search._rerank_by_query_overlap([result], ["火药"])

    assert len(reranked) == 1
    assert reranked[0].metadata["semantic_floor_applied"] is False
    assert reranked[0].similarity_score < 0.3
