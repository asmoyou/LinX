"""Tests for skill-candidate builder."""

from types import SimpleNamespace

from skill_learning.builder import SkillCandidateBuilder


class _BuilderStub:
    def extract_skill_candidates(self, turns, agent_name):
        return [{"title": f"{agent_name}:{len(turns)}"}]

    def build_skill_candidate_observations(
        self, *, agent_id, agent_name, turns, extracted_agent_candidates
    ):
        return (
            [SimpleNamespace(observation_type="skill_candidate")],
            [SimpleNamespace(projection_type="skill_candidate")],
        )


def test_skill_candidate_builder_delegates_to_user_memory_builder():
    builder = SkillCandidateBuilder(builder=_BuilderStub())

    candidates = builder.extract_candidates([{"role": "user", "content": "x"}], "Agent X")
    observations, projections = builder.build_candidates(
        agent_id="agent-1",
        agent_name="Agent X",
        turns=[{"role": "user", "content": "x"}],
        extracted_candidates=candidates,
    )

    assert candidates == [{"title": "Agent X:1"}]
    assert observations[0].observation_type == "skill_candidate"
    assert projections[0].projection_type == "skill_candidate"
