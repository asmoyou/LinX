from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.main import app
from api_gateway.routers import skill_proposals


@pytest.fixture
def current_user():
    return CurrentUser(
        user_id="test-user-id",
        username="tester",
        role="user",
        token_jti="token-jti",
    )


def _proposal_row(
    *,
    row_id: int = 7,
    agent_id: str = "agent-123",
    status: str = "pending_review",
    title: str = "Use headless libreoffice fallback",
    summary: str = "Convert office docs to PDF through headless libreoffice.",
    payload: dict | None = None,
):
    now = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=row_id,
        agent_id=agent_id,
        user_id="user-1",
        proposal_key="libreoffice_fallback",
        owner_type="agent",
        owner_id=agent_id,
        title=title,
        summary=summary,
        details=None,
        status=status,
        published_skill_id=None,
        proposal_payload=payload
        or {
            "goal": title,
            "successful_path": ["detect office doc", "run libreoffice headless", "upload PDF"],
            "why_it_worked": summary,
            "review_status": "pending" if status == "pending_review" else "published",
        },
        created_at=now,
        updated_at=now,
    )


def test_skill_proposal_routes_registered():
    route_paths = {
        (route.path, tuple(sorted(route.methods)))
        for route in app.routes
        if hasattr(route, "methods")
    }

    assert ("/api/v1/skill-proposals", ("GET",)) in route_paths
    assert ("/api/v1/skill-proposals/{memory_id}/review", ("POST",)) in route_paths
    assert ("/api/v1/skill-proposals/{memory_id}/publish", ("POST",)) in route_paths


@pytest.mark.asyncio
async def test_list_skill_proposals_reads_pending_proposals(current_user):
    service = MagicMock()
    service.list_proposals.return_value = [_proposal_row()]

    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = MagicMock()
    session_ctx.__exit__.return_value = False

    with (
        patch(
            "api_gateway.routers.skill_proposals._require_agent_read_access_sync",
            return_value=None,
        ),
        patch(
            "api_gateway.routers.skill_proposals.get_skill_proposal_service",
            return_value=service,
        ),
        patch(
            "database.connection.get_db_session",
            return_value=session_ctx,
        ),
        patch(
            "api_gateway.routers.skill_proposals._lookup_agent_name",
            return_value="Agent X",
        ),
    ):
        response = await skill_proposals.list_skill_proposals(
            agent_id="agent-123",
            review_status="pending",
            limit=20,
            current_user=current_user,
        )

    call_kwargs = service.list_proposals.call_args.kwargs
    assert call_kwargs["agent_ids"] == ["agent-123"]
    assert call_kwargs["review_status"] == "pending"
    assert call_kwargs["limit"] == 20
    assert response[0].type == "skill_proposal"
    assert response[0].metadata["signal_type"] == "skill_proposal"
    assert response[0].metadata["review_status"] == "pending"
    assert "skill.proposal.successful_path" in response[0].content


@pytest.mark.asyncio
async def test_list_skill_proposals_without_agent_id_uses_owned_agents(current_user):
    service = MagicMock()
    service.list_proposals.return_value = [
        _proposal_row(row_id=2, agent_id="agent-b"),
        _proposal_row(row_id=1, agent_id="agent-a"),
    ]

    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = MagicMock()
    session_ctx.__exit__.return_value = False

    with (
        patch(
            "api_gateway.routers.skill_proposals._list_owned_agent_ids_sync",
            return_value=["agent-a", "agent-b"],
        ),
        patch(
            "api_gateway.routers.skill_proposals.get_skill_proposal_service",
            return_value=service,
        ),
        patch("database.connection.get_db_session", return_value=session_ctx),
        patch(
            "api_gateway.routers.skill_proposals._lookup_agent_name",
            side_effect=lambda _session, agent_id: f"name-{agent_id}",
        ),
    ):
        response = await skill_proposals.list_skill_proposals(
            agent_id=None,
            review_status="all",
            limit=10,
            current_user=current_user,
        )

    assert service.list_proposals.call_count == 1
    assert service.list_proposals.call_args.kwargs["agent_ids"] == ["agent-a", "agent-b"]
    assert [item.agent_id for item in response] == ["agent-b", "agent-a"]


@pytest.mark.asyncio
async def test_review_skill_proposal_updates_proposal_and_entry(current_user):
    service = MagicMock()
    proposal = _proposal_row(row_id=9, agent_id="agent-123", status="pending_review")
    updated = _proposal_row(
        row_id=9,
        agent_id="agent-123",
        status="active",
        payload={
            "goal": "Use headless libreoffice fallback",
            "successful_path": ["detect office doc", "run libreoffice headless", "upload PDF"],
            "why_it_worked": "Approved summary",
            "review_status": "published",
        },
    )
    service.get_proposal.return_value = proposal
    service.review_proposal.return_value = updated

    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = MagicMock()
    session_ctx.__exit__.return_value = False

    with (
        patch(
            "api_gateway.routers.skill_proposals._require_agent_read_access_sync",
            return_value=None,
        ),
        patch(
            "api_gateway.routers.skill_proposals._agent_owned_by_user_sync",
            return_value=True,
        ),
        patch(
            "api_gateway.routers.skill_proposals.get_skill_proposal_service",
            return_value=service,
        ),
        patch("database.connection.get_db_session", return_value=session_ctx),
        patch(
            "api_gateway.routers.skill_proposals._lookup_agent_name",
            return_value="Agent X",
        ),
    ):
        request = skill_proposals.AgentCandidateReviewRequest(
            action="publish",
            summary="Approved summary",
            note="ship it",
        )
        response = await skill_proposals.review_skill_proposal(
            memory_id=9,
            request=request,
            current_user=current_user,
        )

    review_kwargs = service.review_proposal.call_args.kwargs
    assert review_kwargs["action"] == "publish"
    assert review_kwargs["reviewer_user_id"] == str(current_user.user_id)
    assert review_kwargs["payload_updates"]["review_note"] == "ship it"
    assert review_kwargs["payload_updates"]["why_it_worked"] == "Approved summary"
    assert response.metadata["review_status"] == "published"
    assert response.type == "skill_proposal"


@pytest.mark.asyncio
async def test_review_skill_proposal_rejects_non_skill_proposal(current_user):
    service = MagicMock()
    service.get_proposal.return_value = SimpleNamespace(
        id=9,
        agent_id="",
    )

    with patch(
        "api_gateway.routers.skill_proposals.get_skill_proposal_service",
        return_value=service,
    ):
        request = skill_proposals.AgentCandidateReviewRequest(action="publish")
        with pytest.raises(skill_proposals.HTTPException) as exc:
            await skill_proposals.review_skill_proposal(
                memory_id=9,
                request=request,
                current_user=current_user,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Skill proposal not found"
