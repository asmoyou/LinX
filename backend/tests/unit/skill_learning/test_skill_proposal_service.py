"""Tests for skill-proposal service."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from skill_learning.service import SkillProposalService


def test_review_proposal_publishes_to_skill_registry_and_updates_proposal():
    repository = MagicMock()
    repository.get_proposal.return_value = SimpleNamespace(
        id=7,
        agent_id="agent-1",
        proposal_key="pdf_delivery",
        title="Stable PDF delivery path",
        goal="Stable PDF delivery path",
        why_it_worked="Try LibreOffice after conversion failures",
        materialized_data={
            "goal": "Stable PDF delivery path",
            "successful_path": ["detect office doc", "run libreoffice headless", "upload PDF"],
        },
        published_skill_id=None,
    )
    repository.update_proposal.return_value = SimpleNamespace(id=7)
    registry = MagicMock()
    registry.get_skill_by_name.return_value = None
    registry.register_skill.return_value = SimpleNamespace(
        skill_id="skill-uuid",
        name="learned_agent_1_pdf_delivery",
    )
    service = SkillProposalService(repository=repository, skill_registry=registry)

    updated = service.review_proposal(
        proposal_id=7,
        action="publish",
        reviewer_user_id="user-1",
        summary="Approved path",
        details=None,
        payload_updates={"review_note": "ship it"},
    )

    assert updated is not None
    registry.register_skill.assert_called_once()
    assert repository.update_proposal.call_args.kwargs["review_status"] == "published"
    assert repository.update_proposal.call_args.kwargs["payload"]["review_status"] == "published"
    assert repository.update_proposal.call_args.kwargs["published_skill_id"] == "skill-uuid"


def test_list_published_experiences_applies_min_score_filter():
    service = SkillProposalService(repository=MagicMock())
    items = [
        SimpleNamespace(similarity_score=0.91, content="a"),
        SimpleNamespace(similarity_score=0.3, content="b"),
    ]

    with patch(
        "skill_learning.service.get_materialized_view_retrieval_service",
        return_value=SimpleNamespace(retrieve_agent_experience=lambda **_: items),
    ):
        results = service.list_published_experiences(
            agent_id="agent-1",
            query_text="pdf",
            limit=5,
            min_score=0.5,
        )

    assert [item.content for item in results] == ["a"]
