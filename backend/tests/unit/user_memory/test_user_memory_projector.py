from datetime import datetime, timezone
from unittest.mock import MagicMock

from user_memory.projector import UserMemoryProjector
from user_memory.session_ledger_repository import MemoryObservationData, SessionLedgerSnapshot


def test_user_memory_projector_builds_entries_and_views_from_observations() -> None:
    builder = MagicMock()
    repo = MagicMock()
    observation = MemoryObservationData(
        observation_key="user.preference.response_style.concise",
        observation_type="user_preference",
        title="用户偏好简洁回答",
    )
    view = MagicMock()
    entry = MagicMock()
    builder.build_user_preference_observations.return_value = ([observation], [view])
    repo._build_entry_from_observation.return_value = entry  # noqa: SLF001

    projector = UserMemoryProjector(builder=builder, session_repository=repo)
    snapshot = SessionLedgerSnapshot(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        status="completed",
    )

    entries, views = projector.project_entries_and_views(
        snapshot=snapshot,
        turns=[{"user_message": "以后请简洁回答"}],
        extracted_signals=[{"key": "response_style", "value": "concise"}],
    )

    assert entries == [entry]
    assert views == [view]
    builder.build_user_preference_observations.assert_called_once()
    repo._build_entry_from_observation.assert_called_once_with(  # noqa: SLF001
        snapshot=snapshot,
        observation=observation,
    )
