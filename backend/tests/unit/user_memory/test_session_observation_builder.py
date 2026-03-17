"""Tests for user-memory extraction normalization."""

from user_memory.session_observation_builder import SessionObservationBuilder


def test_normalize_llm_user_preference_signals_ignores_free_form_llm_key() -> None:
    builder = SessionObservationBuilder()

    signals = builder.normalize_llm_user_preference_signals(
        [
            {
                "fact_kind": "relationship",
                "key": "relationship_friend_xiaochen",
                "value": "小陈",
                "canonical_statement": "用户与小陈是朋友",
                "predicate": "friend",
                "object": "小陈",
                "persons": ["小陈"],
                "persistent": True,
                "explicit_source": True,
                "confidence": 0.93,
                "evidence_turns": [1],
            }
        ],
        {1: "2026-03-10T16:00:00+00:00"},
        max_items=4,
    )

    assert len(signals) == 1
    assert signals[0]["semantic_key"] == "relationship_friend"
    assert signals[0]["identity_signature"] == "relationship|friend|小陈"
    assert signals[0]["key"].startswith("relationship_friend_")
    assert "xiaochen" not in signals[0]["key"]


def test_normalize_llm_user_preference_signals_skips_question_artifacts() -> None:
    builder = SessionObservationBuilder()

    signals = builder.normalize_llm_user_preference_signals(
        [
            {
                "fact_kind": "preference",
                "key": "food_preference_like",
                "value": "什么吗",
                "canonical_statement": "用户偏好food_preference_like是什么吗",
                "persistent": True,
                "explicit_source": True,
                "confidence": 0.95,
                "evidence_turns": [1],
            }
        ],
        {1: "2026-03-17T02:50:00+00:00"},
        max_items=4,
    )

    assert signals == []


def test_extract_user_preference_signals_skips_interrogative_food_queries() -> None:
    builder = SessionObservationBuilder()

    signals = builder.extract_user_preference_signals(
        [
            {
                "user_message": "你知道我喜欢吃什么吗？",
                "agent_response": "我还在回忆。",
                "timestamp": "2026-03-17T02:50:00+00:00",
            }
        ]
    )

    assert signals == []
