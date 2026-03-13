"""Tests for skill-proposal builder."""

from types import SimpleNamespace

from skill_learning.builder import SkillProposalBuilder


class _BuilderStub:
    def extract_skill_proposals(self, turns, agent_name):
        return [{"title": f"{agent_name}:{len(turns)}"}]

    def build_agent_experience_observations(
        self, *, agent_id, agent_name, turns, extracted_agent_candidates
    ):
        return (
            [SimpleNamespace(observation_type="agent_success_path")],
            [SimpleNamespace(materialization_type="agent_experience")],
        )


def test_skill_proposal_builder_delegates_to_user_memory_builder():
    builder = SkillProposalBuilder(builder=_BuilderStub())

    candidates = builder.extract_candidates([{"role": "user", "content": "x"}], "Agent X")
    observations, materializations = builder.build_proposals(
        agent_id="agent-1",
        agent_name="Agent X",
        turns=[{"role": "user", "content": "x"}],
        extracted_candidates=candidates,
    )

    assert candidates == [{"title": "Agent X:1"}]
    assert observations[0].observation_type == "agent_success_path"
    assert materializations[0].materialization_type == "agent_experience"
