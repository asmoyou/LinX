"""Unit tests for agent capability migration to skill IDs."""

from types import SimpleNamespace
from uuid import uuid4

from scripts.migrate_agent_skill_capabilities_to_ids import migrate_agent_capabilities


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, skills, agents):
        self._skills = list(skills)
        self._agents = list(agents)
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        model_name = getattr(model, "__name__", "")
        if model_name == "Skill":
            return _FakeQuery(self._skills)
        if model_name == "Agent":
            return _FakeQuery(self._agents)
        raise AssertionError(f"Unexpected model queried: {model_name}")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *_args):
        return False


def test_migration_maps_skill_slugs_and_preserves_temp_worker_internal_capabilities(
    monkeypatch,
    tmp_path,
):
    skill = SimpleNamespace(skill_id=uuid4(), skill_slug="weather_helper")
    agent = SimpleNamespace(
        agent_id=uuid4(),
        name="Planner",
        agent_type="general",
        capabilities=["weather_helper"],
    )
    temp_worker = SimpleNamespace(
        agent_id=uuid4(),
        name="Temp Worker",
        agent_type="mission_temp_worker",
        capabilities=["weather_helper", "planning"],
    )
    fake_session = _FakeSession(skills=[skill], agents=[agent, temp_worker])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.migrate_agent_skill_capabilities_to_ids.get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    exit_code = migrate_agent_capabilities(dry_run=False)

    assert exit_code == 0
    assert fake_session.committed is True
    assert agent.capabilities == [str(skill.skill_id)]
    assert temp_worker.capabilities == [str(skill.skill_id), "planning"]


def test_migration_fails_for_unmapped_non_temp_agent_capability(monkeypatch, tmp_path):
    agent = SimpleNamespace(
        agent_id=uuid4(),
        name="Analyst",
        agent_type="general",
        capabilities=["missing_skill_slug"],
    )
    fake_session = _FakeSession(skills=[], agents=[agent])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.migrate_agent_skill_capabilities_to_ids.get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    exit_code = migrate_agent_capabilities(dry_run=False)

    assert exit_code == 1
    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert agent.capabilities == ["missing_skill_slug"]
