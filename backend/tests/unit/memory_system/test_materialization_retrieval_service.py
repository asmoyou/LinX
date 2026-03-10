"""Tests for materialized memory retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace

from memory_system.materialization_retrieval_service import MaterializationRetrievalService


class _RepoStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_materializations(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.rows)


def _row(
    *,
    row_id: int,
    owner_type: str,
    owner_id: str,
    materialization_type: str,
    materialization_key: str,
    title: str,
    summary: str = "",
    details: str = "",
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
        materialized_data=dict(payload or {}),
        updated_at=now,
        created_at=now,
    )


def test_user_profile_retrieval_keeps_general_preferences_without_food_noise():
    repo = _RepoStub(
        [
            _row(
                row_id=1,
                owner_type="user",
                owner_id="u-1",
                materialization_type="user_profile",
                materialization_key="response_style",
                title="User preference: response_style",
                summary="concise",
                payload={"key": "response_style", "value": "concise", "confidence": 0.93},
            ),
            _row(
                row_id=2,
                owner_type="user",
                owner_id="u-1",
                materialization_type="user_profile",
                materialization_key="favorite_food",
                title="User preference: favorite_food",
                summary="spicy hotpot",
                payload={"key": "favorite_food", "value": "spicy hotpot", "confidence": 0.88},
            ),
        ]
    )
    service = MaterializationRetrievalService(repository=repo)

    results = service.retrieve_user_profile(
        user_id="u-1",
        query_text="Write a short summary for this document",
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].content == "user.preference.response_style=concise"
    assert results[0].metadata["materialization_type"] == "user_profile"


def test_agent_experience_retrieval_matches_success_path_query():
    repo = _RepoStub(
        [
            _row(
                row_id=3,
                owner_type="agent",
                owner_id="a-1",
                materialization_type="agent_experience",
                materialization_key="pdf_delivery",
                title="Stable PDF delivery path",
                summary="Switch to the converter that preserved attachments and verify output.",
                details="inspect input -> switch converter -> verify delivered file",
                payload={
                    "goal": "Stable PDF delivery path",
                    "successful_path": [
                        "inspect input constraints",
                        "switch converter",
                        "verify delivered file",
                    ],
                    "why_it_worked": "The chosen converter preserved attachments.",
                    "applicability": "Repeated file conversion failures",
                    "avoid": "Do not retry the unstable converter",
                    "importance": 0.82,
                },
            ),
            _row(
                row_id=4,
                owner_type="agent",
                owner_id="a-1",
                materialization_type="agent_experience",
                materialization_key="calendar_booking",
                title="Calendar booking path",
                summary="Book the meeting after validating timezone.",
                payload={"goal": "Calendar booking path"},
            ),
        ]
    )
    service = MaterializationRetrievalService(repository=repo)

    results = service.retrieve_agent_experience(
        agent_id="a-1",
        query_text="Need a reliable way to convert pdf and deliver the file",
        top_k=5,
    )

    assert len(results) == 1
    assert "agent.experience.goal=Stable PDF delivery path" in results[0].content
    assert "agent.experience.successful_path=" in results[0].content
    assert results[0].metadata["materialization_key"] == "pdf_delivery"
