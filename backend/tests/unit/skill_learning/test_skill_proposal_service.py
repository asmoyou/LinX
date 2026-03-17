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
        proposal_payload={
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

    with patch.object(
        service,
        "_upload_agent_skill_package",
        return_value="skills/learned_agent_1_pdf_delivery/1.0.0/package.zip",
    ) as upload_package:
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
    upload_package.assert_called_once()
    assert repository.update_proposal.call_args.kwargs["review_status"] == "published"
    assert repository.update_proposal.call_args.kwargs["payload"]["review_status"] == "published"
    assert repository.update_proposal.call_args.kwargs["published_skill_id"] == "skill-uuid"
    register_kwargs = registry.register_skill.call_args.kwargs
    assert register_kwargs["storage_type"] == "minio"
    assert register_kwargs["storage_path"] == "skills/learned_agent_1_pdf_delivery/1.0.0/package.zip"


def test_list_published_skills_reads_registry_backed_runtime_items():
    repository = MagicMock()
    repository.list_proposals.return_value = [
        SimpleNamespace(
            id=7,
            agent_id="agent-1",
            user_id="user-1",
            proposal_key="pdf_delivery",
            title="Stable PDF delivery path",
            goal="Stable PDF delivery path",
            why_it_worked="Switch converter and verify output.",
            proposal_payload={
                "goal": "Stable PDF delivery path",
                "successful_path": ["inspect input constraints", "switch converter"],
                "why_it_worked": "Switch converter and verify output.",
                "confidence": 0.9,
            },
            published_skill_id="7f9f8b89-0f13-4c95-a827-2199efd28475",
            review_status="published",
            updated_at=None,
            created_at=None,
        )
    ]
    registry = MagicMock()
    registry.get_skill.return_value = SimpleNamespace(
        skill_id="7f9f8b89-0f13-4c95-a827-2199efd28475",
        name="learned_agent_1_pdf_delivery",
        description="Stable PDF delivery path: Switch converter and verify output.",
        skill_type="agent_skill",
        storage_type="inline",
        skill_md_content="# Stable PDF delivery path",
        is_active=True,
        updated_at=None,
        created_at=None,
    )
    service = SkillProposalService(repository=repository, skill_registry=registry)

    results = service.list_published_skills(
        agent_id="agent-1",
        query_text="reliable pdf delivery path",
        limit=5,
        min_score=0.5,
    )

    assert len(results) == 1
    assert results[0].memory_type == "published_skill"
    assert results[0].metadata["skill_name"] == "learned_agent_1_pdf_delivery"
    assert "learned.skill.goal=Stable PDF delivery path" in results[0].content
