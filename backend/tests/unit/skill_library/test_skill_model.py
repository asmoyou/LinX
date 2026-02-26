"""Unit tests for SkillModel database behaviors."""

from types import SimpleNamespace
from uuid import uuid4

from skill_library.skill_model import SkillModel


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, skill=None, agents=None):
        self._skill = skill
        self._agents = list(agents or [])
        self.deleted = []
        self.committed = False

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "Skill":
            return _FakeQuery([self._skill] if self._skill is not None else [])
        if model_name == "Agent":
            return _FakeQuery(self._agents)
        raise AssertionError(f"Unexpected model queried: {model_name}")

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed = True


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *_args):
        return False


def test_delete_skill_returns_false_when_missing(monkeypatch):
    model = SkillModel()
    fake_session = _FakeSession(skill=None, agents=[])
    monkeypatch.setattr(
        "skill_library.skill_model.get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    result = model.delete_skill(uuid4())

    assert result is False
    assert fake_session.deleted == []
    assert fake_session.committed is False


def test_delete_skill_detaches_deleted_skill_from_agent_capabilities(monkeypatch):
    model = SkillModel()
    deleted_skill_name = "weather-forcast"
    fake_skill = SimpleNamespace(skill_id=uuid4(), name=deleted_skill_name)
    agent_with_skill = SimpleNamespace(
        agent_id=uuid4(),
        capabilities=[deleted_skill_name, "other-skill"],
    )
    agent_without_skill = SimpleNamespace(
        agent_id=uuid4(),
        capabilities=["other-skill"],
    )
    fake_session = _FakeSession(
        skill=fake_skill,
        agents=[agent_with_skill, agent_without_skill],
    )
    monkeypatch.setattr(
        "skill_library.skill_model.get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    result = model.delete_skill(fake_skill.skill_id)

    assert result is True
    assert fake_session.deleted == [fake_skill]
    assert fake_session.committed is True
    assert agent_with_skill.capabilities == ["other-skill"]
    assert agent_without_skill.capabilities == ["other-skill"]
