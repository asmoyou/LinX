"""Tests for multilingual-aware retrieval heuristics and query expansion."""

from knowledge_base.knowledge_search import KnowledgeSearch, SearchFilter, SearchResult


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
