"""Tests for materialized user-memory and skill-view retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.materialized_view_retrieval import MaterializedViewRetrievalService


class _RepoStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_materializations(self, **kwargs):
        self.calls.append(kwargs)
        rows = list(self.rows)
        materialization_type = kwargs.get("materialization_type")
        status = kwargs.get("status")
        if materialization_type:
            rows = [
                row for row in rows if str(row.materialization_type) == str(materialization_type)
            ]
        if status:
            rows = [row for row in rows if str(row.status) == str(status)]
        return rows


def _row(
    *,
    row_id: int,
    owner_type: str,
    owner_id: str,
    materialization_type: str,
    materialization_key: str,
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
        materialization_type=materialization_type,
        materialization_key=materialization_key,
        title=title,
        summary=summary,
        details=details,
        status=status,
        materialized_data=dict(payload or {}),
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
                materialization_type="user_profile",
                materialization_key="response_style",
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
    service = MaterializedViewRetrievalService(repository=repo)

    results = service.retrieve_user_profile(user_id="u-1", query_text="写得简洁一点", top_k=5)

    assert len(results) == 1
    assert results[0].memory_type == "user_memory"
    assert results[0].metadata["record_type"] == "user_profile"


def test_agent_experience_retrieval_returns_skill_experience_items() -> None:
    repo = _RepoStub(
        [
            _row(
                row_id=2,
                owner_type="agent",
                owner_id="a-1",
                materialization_type="agent_experience",
                materialization_key="pdf_delivery",
                title="Stable PDF delivery path",
                summary="Switch converter and verify output.",
                payload={
                    "goal": "Stable PDF delivery path",
                    "successful_path": [
                        "inspect input constraints",
                        "switch converter",
                        "verify delivered file",
                    ],
                    "why_it_worked": "Switch converter and verify output.",
                    "confidence": 0.84,
                },
            )
        ]
    )
    service = MaterializedViewRetrievalService(repository=repo)

    results = service.retrieve_agent_experience(
        agent_id="a-1",
        query_text="reliable pdf delivery path",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].memory_type == "skill_experience"
    assert results[0].metadata["record_type"] == "agent_experience"
