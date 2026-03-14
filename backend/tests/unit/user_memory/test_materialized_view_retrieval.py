"""Tests for user-memory view retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.user_memory_view_retrieval import UserMemoryViewRetrievalService


class _RepoStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_projections(self, **kwargs):
        self.calls.append(kwargs)
        rows = list(self.rows)
        view_type = kwargs.get("projection_type")
        status = kwargs.get("status")
        if view_type:
            rows = [row for row in rows if str(row.view_type) == str(view_type)]
        if status:
            rows = [row for row in rows if str(row.status) == str(status)]
        return rows


def _row(
    *,
    row_id: int,
    owner_type: str,
    owner_id: str,
    view_type: str,
    view_key: str,
    title: str = "",
    summary: str = "",
    details: str = "",
    status: str = "active",
    payload=None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=row_id,
        owner_type=owner_type,
        owner_id=owner_id,
        view_type=view_type,
        view_key=view_key,
        title=title,
        summary=summary,
        details=details,
        status=status,
        view_data=dict(payload or {}),
        updated_at=now,
        created_at=now,
    )


def test_user_profile_retrieval_returns_user_memory_items() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=1,
                owner_type="user",
                owner_id="u-1",
                view_type="user_profile",
                view_key="response_style",
                summary="concise",
                payload={
                    "key": "response_style",
                    "value": "concise",
                    "canonical_statement": "user.preference.response_style=concise",
                    "confidence": 0.91,
                },
            )
        ]
    )
    service = UserMemoryViewRetrievalService(repository=repo)

    results = service.retrieve_user_profile(user_id="u-1", query_text="写得简洁一点", top_k=5)

    assert len(results) == 1
    assert results[0].memory_type == "user_memory"
    assert results[0].metadata["record_type"] == "user_profile"
    assert results[0].metadata["view_type"] == "user_profile"


def test_user_episode_retrieval_returns_episode_views() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=3,
                owner_type="user",
                owner_id="u-1",
                view_type="episode",
                view_key="episode_move_hz",
                title="2024年8月 · 迁居",
                summary="在2024年8月，搬到了杭州",
                payload={
                    "value": "搬到了杭州",
                    "fact_kind": "event",
                    "canonical_statement": "在2024年8月，搬到了杭州",
                    "event_time": "2024年8月",
                    "location": "杭州",
                    "topic": "迁居",
                    "confidence": 0.89,
                },
            )
        ]
    )
    service = UserMemoryViewRetrievalService(repository=repo)

    results = service.retrieve_user_episodes(
        user_id="u-1",
        query_text="什么时候搬到杭州",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].memory_type == "user_memory"
    assert results[0].content == "在2024年8月，搬到了杭州"
    assert results[0].metadata["record_type"] == "episode"
    assert results[0].metadata["view_type"] == "episode"
    assert results[0].metadata["event_time"] == "2024年8月"
