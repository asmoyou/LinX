"""Tests for atomic memory-entry retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.memory_entry_retrieval import MemoryEntryRetrievalService


class _RepoStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_entries(self, **kwargs):
        self.calls.append(kwargs)
        rows = list(self.rows)
        entry_type = kwargs.get("entry_type")
        status = kwargs.get("status")
        if entry_type:
            rows = [row for row in rows if str(row.entry_type) == str(entry_type)]
        if status:
            rows = [row for row in rows if str(row.status) == str(status)]
        return rows


def _row(
    *,
    row_id: int,
    owner_type: str,
    owner_id: str,
    entry_type: str,
    entry_key: str,
    canonical_text: str,
    status: str = "active",
    summary: str = "",
    details: str = "",
    payload=None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=row_id,
        owner_type=owner_type,
        owner_id=owner_id,
        entry_type=entry_type,
        entry_key=entry_key,
        canonical_text=canonical_text,
        summary=summary,
        details=details,
        status=status,
        entry_data=dict(payload or {}),
        updated_at=now,
        created_at=now,
    )


def test_user_fact_retrieval_prefers_general_profile_entries() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=1,
                owner_type="user",
                owner_id="u-1",
                entry_type="user_fact",
                entry_key="response_style",
                canonical_text="user.preference.response_style=concise",
                summary="concise",
                payload={"key": "response_style", "value": "concise", "confidence": 0.93},
            ),
            _row(
                row_id=2,
                owner_type="user",
                owner_id="u-1",
                entry_type="user_fact",
                entry_key="favorite_food",
                canonical_text="user.preference.favorite_food=spicy hotpot",
                summary="spicy hotpot",
                payload={"key": "favorite_food", "value": "spicy hotpot", "confidence": 0.88},
            ),
        ]
    )
    service = MemoryEntryRetrievalService(repository=repo)

    results = service.retrieve_user_facts(
        user_id="u-1",
        query_text="Write a short summary for this document",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].content == "user.preference.response_style=concise"
    assert results[0].memory_type == "user_memory"
    assert results[0].metadata["entry_type"] == "user_fact"


def test_user_fact_retrieval_supports_canonical_relationship_statement() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=11,
                owner_type="user",
                owner_id="u-1",
                entry_type="user_fact",
                entry_key="relationship_spouse",
                canonical_text="用户的配偶是王敏",
                summary="用户的配偶是王敏",
                payload={
                    "key": "relationship_spouse",
                    "value": "王敏",
                    "fact_kind": "relationship",
                    "canonical_statement": "用户的配偶是王敏",
                    "confidence": 0.95,
                },
            )
        ]
    )
    service = MemoryEntryRetrievalService(repository=repo)

    results = service.retrieve_user_facts(
        user_id="u-1",
        query_text="用户的配偶是谁",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].content == "用户的配偶是王敏"
    assert results[0].metadata["fact_kind"] == "relationship"


def test_user_fact_retrieval_supports_timed_event_statement() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=12,
                owner_type="user",
                owner_id="u-1",
                entry_type="user_fact",
                entry_key="important_event_123",
                canonical_text="在2024年8月，搬到了杭州",
                summary="在2024年8月，搬到了杭州",
                payload={
                    "key": "important_event_123",
                    "value": "搬到了杭州",
                    "fact_kind": "event",
                    "canonical_statement": "在2024年8月，搬到了杭州",
                    "event_time": "2024年8月",
                    "location": "杭州",
                    "confidence": 0.88,
                },
            )
        ]
    )
    service = MemoryEntryRetrievalService(repository=repo)

    results = service.retrieve_user_facts(
        user_id="u-1",
        query_text="用户是什么时候搬到杭州的",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].content == "在2024年8月，搬到了杭州"
    assert results[0].metadata["fact_kind"] == "event"
    assert results[0].metadata["event_time"] == "2024年8月"


def test_agent_skill_candidate_retrieval_ignores_pending_when_active_requested() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=3,
                owner_type="agent",
                owner_id="a-1",
                entry_type="agent_skill_candidate",
                entry_key="pdf_delivery",
                canonical_text=(
                    "agent.experience.goal=Stable PDF delivery path\n"
                    "agent.experience.successful_path=inspect input constraints | switch converter | verify delivered file"
                ),
                summary="Switch to the converter that preserved attachments and verify output.",
                payload={
                    "goal": "Stable PDF delivery path",
                    "successful_path": [
                        "inspect input constraints",
                        "switch converter",
                        "verify delivered file",
                    ],
                    "review_status": "published",
                    "confidence": 0.82,
                },
                status="active",
            ),
            _row(
                row_id=4,
                owner_type="agent",
                owner_id="a-1",
                entry_type="agent_skill_candidate",
                entry_key="calendar_booking",
                canonical_text="agent.experience.goal=Calendar booking path",
                summary="Book the meeting after validating timezone.",
                payload={"goal": "Calendar booking path", "review_status": "pending"},
                status="pending_review",
            ),
        ]
    )
    service = MemoryEntryRetrievalService(repository=repo)

    results = service.retrieve_agent_skill_candidates(
        agent_id="a-1",
        query_text="Need a reliable way to convert pdf and deliver the file",
        top_k=5,
        status="active",
    )

    assert len(results) == 1
    assert "Stable PDF delivery path" in results[0].content
    assert results[0].memory_type == "skill_experience"
    assert results[0].metadata["entry_key"] == "pdf_delivery"
    assert repo.calls[0]["status"] == "active"
