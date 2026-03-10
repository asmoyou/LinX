"""Tests for materialization backfill and consolidation maintenance."""

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from memory_system.materialization_maintenance_service import (
    MaterializationMaintenanceService,
)
from memory_system.memory_interface import MemoryType
from memory_system.memory_repository import MemoryRecordData


class _MemoryRepoStub:
    def __init__(self, *, user_rows=None, agent_rows=None):
        self._user_rows = list(user_rows or [])
        self._agent_rows = list(agent_rows or [])

    def list_memories(self, *, memory_type=None, **kwargs):  # noqa: ANN003
        if memory_type == MemoryType.USER_CONTEXT:
            return list(self._user_rows)
        if memory_type == MemoryType.AGENT:
            return list(self._agent_rows)
        return []


class _SessionRepoStub:
    def __init__(self, *, materializations=None, entries=None):
        self.upserts = []
        self.entry_upserts = []
        self.updates = []
        self.entry_updates = []
        self._materializations = list(materializations or [])
        self._entries = list(entries or [])

    def upsert_materialization(
        self, *, materialization, source_session_id=None, source_observation_id=None
    ):
        self.upserts.append(materialization)
        return len(self.upserts)

    def upsert_entry(self, *, entry, source_session_id=None, source_observation_id=None):
        self.entry_upserts.append(entry)
        return len(self.entry_upserts)

    def list_materializations(self, **kwargs):  # noqa: ANN003
        owner_type = kwargs.get("owner_type")
        owner_id = kwargs.get("owner_id")
        materialization_type = kwargs.get("materialization_type")
        rows = self._materializations
        if owner_type:
            rows = [row for row in rows if str(row.owner_type) == str(owner_type)]
        if owner_id:
            rows = [row for row in rows if str(row.owner_id) == str(owner_id)]
        if materialization_type:
            rows = [
                row for row in rows if str(row.materialization_type) == str(materialization_type)
            ]
        return list(rows)

    def list_entries(self, **kwargs):  # noqa: ANN003
        owner_type = kwargs.get("owner_type")
        owner_id = kwargs.get("owner_id")
        entry_type = kwargs.get("entry_type")
        rows = self._entries
        if owner_type:
            rows = [row for row in rows if str(row.owner_type) == str(owner_type)]
        if owner_id:
            rows = [row for row in rows if str(row.owner_id) == str(owner_id)]
        if entry_type:
            rows = [row for row in rows if str(row.entry_type) == str(entry_type)]
        return list(rows)

    def update_materialization(self, materialization_id, **kwargs):  # noqa: ANN003
        self.updates.append({"materialization_id": materialization_id, **kwargs})
        return SimpleNamespace(id=materialization_id, **kwargs)

    def update_entry(self, entry_id, **kwargs):  # noqa: ANN003
        self.entry_updates.append({"entry_id": entry_id, **kwargs})
        return SimpleNamespace(id=entry_id, **kwargs)


def _legacy_row(
    *,
    memory_id: int,
    memory_type: MemoryType,
    content: str,
    user_id: str | None = None,
    agent_id: str | None = None,
    metadata=None,
    timestamp: datetime | None = None,
) -> MemoryRecordData:
    now = timestamp or datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    return MemoryRecordData(
        id=memory_id,
        milvus_id=memory_id + 1000,
        memory_type=memory_type,
        content=content,
        user_id=user_id,
        agent_id=agent_id,
        task_id=None,
        owner_user_id=user_id,
        owner_agent_id=agent_id,
        department_id=None,
        visibility="private",
        sensitivity="internal",
        source_memory_id=None,
        expires_at=None,
        metadata=dict(metadata or {}),
        timestamp=now,
        vector_status="synced",
        vector_error=None,
        vector_updated_at=now,
    )


def _materialization_row(
    *,
    materialization_id: int,
    owner_type: str,
    owner_id: str,
    materialization_type: str,
    materialization_key: str,
    title: str,
    payload,
    status: str = "active",
):
    now = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=materialization_id,
        owner_type=owner_type,
        owner_id=owner_id,
        materialization_type=materialization_type,
        materialization_key=materialization_key,
        title=title,
        summary=payload.get("value") or payload.get("why_it_worked"),
        details=None,
        status=status,
        materialized_data=dict(payload),
        updated_at=now,
        created_at=now,
    )


def _entry_row(
    *,
    entry_id: int,
    owner_type: str,
    owner_id: str,
    entry_type: str,
    entry_key: str,
    canonical_text: str,
    payload,
    status: str = "active",
):
    now = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=entry_id,
        owner_type=owner_type,
        owner_id=owner_id,
        entry_type=entry_type,
        entry_key=entry_key,
        canonical_text=canonical_text,
        summary=payload.get("value") or payload.get("why_it_worked"),
        details=None,
        status=status,
        entry_data=dict(payload),
        updated_at=now,
        created_at=now,
    )


def test_materialization_maintenance_backfills_latest_user_and_agent_records() -> None:
    older = _legacy_row(
        memory_id=1,
        memory_type=MemoryType.USER_CONTEXT,
        user_id="user-1",
        content="user.preference.response_style=detailed",
        metadata={
            "signal_type": "user_preference",
            "preference_key": "response_style",
            "preference_value": "detailed",
            "confidence": 0.7,
            "is_active": False,
            "latest_turn_ts": "2026-03-01T10:00:00Z",
        },
    )
    newer = replace(
        older,
        id=2,
        content="user.preference.response_style=concise",
        metadata={
            "signal_type": "user_preference",
            "preference_key": "response_style",
            "preference_value": "concise",
            "confidence": 0.92,
            "is_active": True,
            "strong_signal": True,
            "latest_turn_ts": "2026-03-09T10:00:00Z",
        },
        timestamp=datetime(2026, 3, 9, 10, 0, 0, tzinfo=timezone.utc),
    )
    agent_row = _legacy_row(
        memory_id=3,
        memory_type=MemoryType.AGENT,
        user_id="user-1",
        agent_id="agent-1",
        content=(
            "interaction.sop.title=Stable PDF delivery path\n"
            "interaction.sop.steps=识别限制 | 切换稳定链路 | 校验后交付\n"
            "interaction.sop.summary=先识别失败原因，再走稳定转换路径。"
        ),
        metadata={
            "signal_type": "agent_memory_candidate",
            "candidate_title": "Stable PDF delivery path",
            "candidate_fingerprint": "pdf_delivery",
            "candidate_summary": "先识别失败原因，再走稳定转换路径。",
            "review_status": "published",
            "confidence": 0.88,
        },
    )
    session_repo = _SessionRepoStub()
    service = MaterializationMaintenanceService(
        session_repository=session_repo,
        memory_repository=_MemoryRepoStub(user_rows=[older, newer], agent_rows=[agent_row]),
    )

    result = service.backfill_materializations(dry_run=False)

    assert result.user_profile_upserts == 1
    assert result.agent_experience_upserts == 1
    assert result.user_entry_upserts == 1
    assert result.agent_entry_upserts == 1
    assert len(session_repo.upserts) == 2
    assert len(session_repo.entry_upserts) == 2
    assert session_repo.upserts[0].summary == "concise"
    assert session_repo.upserts[0].status == "active"
    assert session_repo.upserts[1].materialization_key == "pdf_delivery"
    assert session_repo.upserts[1].status == "active"
    assert session_repo.upserts[1].payload["review_status"] == "published"
    assert session_repo.entry_upserts[0].entry_key == "response_style"
    assert session_repo.entry_upserts[1].entry_key == "pdf_delivery"
    assert session_repo.entry_upserts[1].status == "active"


def test_materialization_maintenance_consolidates_duplicate_agent_experiences() -> None:
    canonical = _materialization_row(
        materialization_id=11,
        owner_type="agent",
        owner_id="agent-1",
        materialization_type="agent_experience",
        materialization_key="pdf_delivery_v2",
        title="Stable PDF delivery path",
        payload={
            "goal": "Stable PDF delivery path",
            "successful_path": ["识别限制", "切换稳定链路", "校验后交付"],
            "review_status": "published",
            "confidence": 0.91,
        },
        status="active",
    )
    duplicate = _materialization_row(
        materialization_id=12,
        owner_type="agent",
        owner_id="agent-1",
        materialization_type="agent_experience",
        materialization_key="pdf_delivery_old",
        title="Stable PDF delivery path",
        payload={
            "goal": "Stable PDF delivery path",
            "successful_path": ["识别限制", "切换稳定链路", "校验后交付"],
            "review_status": "pending",
            "confidence": 0.72,
        },
        status="pending_review",
    )
    user_entry_old = _entry_row(
        entry_id=20,
        owner_type="user",
        owner_id="user-1",
        entry_type="user_fact",
        entry_key="response_style",
        canonical_text="user.preference.response_style=detailed",
        payload={
            "key": "response_style",
            "value": "detailed",
            "is_active": False,
            "confidence": 0.72,
        },
        status="active",
    )
    user_entry_new = _entry_row(
        entry_id=21,
        owner_type="user",
        owner_id="user-1",
        entry_type="user_fact",
        entry_key="response_style",
        canonical_text="user.preference.response_style=concise",
        payload={
            "key": "response_style",
            "value": "concise",
            "is_active": True,
            "confidence": 0.92,
        },
        status="active",
    )
    agent_entry_canonical = _entry_row(
        entry_id=30,
        owner_type="agent",
        owner_id="agent-1",
        entry_type="agent_skill_candidate",
        entry_key="pdf_delivery_v2",
        canonical_text="agent.experience.goal=Stable PDF delivery path",
        payload={
            "goal": "Stable PDF delivery path",
            "successful_path": ["识别限制", "切换稳定链路", "校验后交付"],
            "review_status": "published",
            "confidence": 0.91,
        },
        status="active",
    )
    agent_entry_duplicate = _entry_row(
        entry_id=31,
        owner_type="agent",
        owner_id="agent-1",
        entry_type="agent_skill_candidate",
        entry_key="pdf_delivery_old",
        canonical_text="agent.experience.goal=Stable PDF delivery path",
        payload={
            "goal": "Stable PDF delivery path",
            "successful_path": ["识别限制", "切换稳定链路", "校验后交付"],
            "review_status": "pending",
            "confidence": 0.72,
        },
        status="pending_review",
    )
    session_repo = _SessionRepoStub(
        materializations=[canonical, duplicate],
        entries=[user_entry_old, user_entry_new, agent_entry_canonical, agent_entry_duplicate],
    )
    service = MaterializationMaintenanceService(
        session_repository=session_repo,
        memory_repository=_MemoryRepoStub(),
    )

    result = service.consolidate_materializations(dry_run=False, agent_id="agent-1")

    assert result.agent_duplicate_supersedes == 1
    assert result.user_entry_status_updates == 1
    assert result.agent_duplicate_entry_supersedes == 1
    assert any(
        update["materialization_id"] == 12 and update.get("status") == "superseded"
        for update in session_repo.updates
    )
    assert any(
        update["materialization_id"] == 11
        and "merged_materialization_ids" in update.get("payload", {})
        for update in session_repo.updates
    )
    assert any(
        update["entry_id"] == 20 and update.get("status") == "superseded"
        for update in session_repo.entry_updates
    )
    assert any(
        update["entry_id"] == 31 and update.get("status") == "superseded"
        for update in session_repo.entry_updates
    )


def test_materialization_maintenance_syncs_reviewed_candidate_into_materialization() -> None:
    session_repo = _SessionRepoStub()
    service = MaterializationMaintenanceService(
        session_repository=session_repo,
        memory_repository=_MemoryRepoStub(),
    )
    record = _legacy_row(
        memory_id=20,
        memory_type=MemoryType.AGENT,
        user_id="user-1",
        agent_id="agent-1",
        content=(
            "interaction.sop.title=Calendar booking path\n"
            "interaction.sop.steps=确认时间窗口 | 发出候选时间 | 最终确认\n"
            "interaction.sop.summary=先收集约束，再推进确认。"
        ),
        metadata={
            "signal_type": "agent_memory_candidate",
            "candidate_fingerprint": "calendar_booking",
            "review_status": "pending",
            "confidence": 0.8,
        },
    )

    materialization_id = service.sync_agent_candidate_materialization(
        record=record,
        review_status="published",
    )

    assert materialization_id == 1
    assert session_repo.upserts[0].status == "active"
    assert session_repo.upserts[0].payload["review_status"] == "published"
    assert session_repo.entry_upserts[0].status == "active"
    assert session_repo.entry_upserts[0].entry_key == "calendar_booking"
