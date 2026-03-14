from types import SimpleNamespace
from unittest.mock import MagicMock

from skill_learning.service import SkillProposalService


def test_skill_learning_publish_flow_promotes_proposal_into_skill_registry() -> None:
    proposal = SimpleNamespace(
        id=7,
        agent_id="agent-1",
        user_id="user-1",
        proposal_key="stable_pdf_delivery_path",
        title="稳定 PDF 转换交付路径",
        goal="稳定 PDF 转换交付",
        why_it_worked="分层兜底避免单一路径失败。",
        applicability="文件转换与交付场景",
        avoid="不要只依赖单一转换器",
        published_skill_id=None,
        proposal_payload={
            "goal": "稳定 PDF 转换交付",
            "successful_path": ["优先 libreoffice", "失败切图像中转", "最终上传 PDF"],
            "why_it_worked": "分层兜底避免单一路径失败。",
        },
    )
    repository = MagicMock()
    repository.get_proposal.return_value = proposal
    repository.update_proposal.return_value = SimpleNamespace(published_skill_id="skill-1")
    skill_registry = MagicMock()
    skill_registry.get_skill.return_value = None
    skill_registry.get_skill_by_name.return_value = None
    skill_registry.register_skill.return_value = SimpleNamespace(
        skill_id="skill-1", name="learned_agent_1_stable_pdf_delivery_path"
    )

    service = SkillProposalService(repository=repository, skill_registry=skill_registry)
    updated = service.publish_proposal(
        proposal_id=7,
        reviewer_user_id="reviewer-1",
        summary=None,
        details=None,
        payload_updates={},
    )

    assert updated.published_skill_id == "skill-1"
    register_kwargs = skill_registry.register_skill.call_args.kwargs
    assert register_kwargs["skill_type"] == "agent_skill"
    assert register_kwargs["storage_type"] == "inline"
    assert register_kwargs["config"]["proposal_id"] == 7
    assert repository.update_proposal.call_args.kwargs["published_skill_id"] == "skill-1"
