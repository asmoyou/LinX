from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.projection_maintenance_service import ProjectionMaintenanceService
from user_memory.session_ledger_repository import SessionLedgerRepository


class _RepoStub:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.user_views = [
            SimpleNamespace(
                id=1,
                owner_id="u-1",
                owner_type="user",
                view_type="user_profile",
                view_key="response_style",
                title="User preference: response_style",
                summary="concise",
                status="active",
                view_data={"is_active": False, "confidence": 0.7},
                created_at=now,
                updated_at=now,
                content="concise",
            ),
            SimpleNamespace(
                id=2,
                owner_id="u-1",
                owner_type="user",
                view_type="user_profile",
                view_key="relationship_acquaintance_xiaochen",
                title="用户明天将和小陈一起外出",
                summary="用户明天将和小陈一起外出",
                status="active",
                view_data={
                    "key": "relationship_acquaintance_xiaochen",
                    "semantic_key": "relationship_acquaintance_xiaochen",
                    "fact_kind": "relationship",
                    "predicate": "associate",
                    "value": "小陈",
                    "object": "小陈",
                    "canonical_statement": "用户明天将和小陈一起外出",
                    "event_time": None,
                    "is_active": True,
                },
                created_at=now,
                updated_at=now,
                content="用户明天将和小陈一起外出",
            ),
            SimpleNamespace(
                id=3,
                owner_id="u-1",
                owner_type="user",
                view_type="user_profile",
                view_key="preference_drink_cola",
                title="用户喜欢喝可乐",
                summary="用户喜欢喝可乐",
                status="active",
                view_data={
                    "key": "preference_drink_cola",
                    "semantic_key": "preference_drink_cola",
                    "fact_kind": "preference",
                    "canonical_statement": "用户喜欢喝可乐",
                    "is_active": True,
                    "confidence": 0.78,
                },
                created_at=now,
                updated_at=now,
                content="用户喜欢喝可乐",
            ),
            SimpleNamespace(
                id=4,
                owner_id="u-1",
                owner_type="user",
                view_type="user_profile",
                view_key="preference_drink_coke",
                title="用户喜欢喝可乐",
                summary="用户喜欢喝可乐",
                status="active",
                view_data={
                    "key": "preference_drink_coke",
                    "semantic_key": "preference_drink_coke",
                    "fact_kind": "preference",
                    "canonical_statement": "用户喜欢喝可乐",
                    "is_active": True,
                    "confidence": 0.86,
                },
                created_at=now,
                updated_at=now,
                content="用户喜欢喝可乐",
            ),
        ]
        self.skill_proposals = [
            SimpleNamespace(
                id=10,
                owner_id="a-1",
                owner_type="agent",
                agent_id="a-1",
                proposal_key="pdf-path-a",
                title="Stable PDF delivery",
                summary="Stable PDF delivery",
                details=None,
                status="active",
                proposal_payload={
                    "goal": "Stable PDF delivery",
                    "successful_path": ["inspect", "convert", "verify"],
                    "confidence": 0.9,
                    "review_status": "published",
                },
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=11,
                owner_id="a-1",
                owner_type="agent",
                agent_id="a-1",
                proposal_key="pdf-path-b",
                title="Stable PDF delivery",
                summary="Stable PDF delivery",
                details=None,
                status="pending_review",
                proposal_payload={
                    "goal": "Stable PDF delivery",
                    "successful_path": ["inspect", "convert", "verify"],
                    "confidence": 0.6,
                    "review_status": "pending",
                },
                created_at=now,
                updated_at=now,
            ),
        ]
        self.user_entries = [
            SimpleNamespace(
                id=20,
                owner_id="u-1",
                owner_type="user",
                entry_type="user_fact",
                fact_kind="preference",
                entry_key="response_style",
                summary="concise",
                status="active",
                entry_data={"key": "response_style", "is_active": False, "confidence": 0.7},
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=22,
                owner_id="u-1",
                owner_type="user",
                entry_type="user_fact",
                fact_kind="relationship",
                entry_key="relationship_acquaintance_xiaochen",
                canonical_text="用户明天将和小陈一起外出",
                summary="用户明天将和小陈一起外出",
                event_time=None,
                predicate="associate",
                object_text="小陈",
                status="active",
                entry_data={
                    "key": "relationship_acquaintance_xiaochen",
                    "semantic_key": "relationship_acquaintance_xiaochen",
                    "value": "小陈",
                    "fact_kind": "relationship",
                    "predicate": "associate",
                    "object": "小陈",
                    "canonical_statement": "用户明天将和小陈一起外出",
                    "event_time": None,
                    "is_active": True,
                },
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=21,
                owner_id="u-1",
                owner_type="user",
                entry_type="user_fact",
                fact_kind="event",
                entry_key="life_event_move_abc123",
                canonical_text="在2024年8月，搬到了杭州",
                summary="在2024年8月，搬到了杭州",
                event_time="2024年8月",
                topic="迁居",
                location="杭州",
                confidence=0.88,
                importance=0.91,
                status="active",
                entry_data={
                    "key": "life_event_move_abc123",
                    "value": "搬到了杭州",
                    "fact_kind": "event",
                    "canonical_statement": "在2024年8月，搬到了杭州",
                    "event_time": "2024年8月",
                    "topic": "迁居",
                    "location": "杭州",
                    "confidence": 0.88,
                    "importance": 0.91,
                    "is_active": True,
                },
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=23,
                owner_id="u-1",
                owner_type="user",
                entry_type="user_fact",
                fact_kind="preference",
                entry_key="preference_drink_cola",
                canonical_text="用户喜欢喝可乐",
                summary="用户喜欢喝可乐",
                status="active",
                entry_data={
                    "key": "preference_drink_cola",
                    "semantic_key": "preference_drink_cola",
                    "value": "可乐",
                    "fact_kind": "preference",
                    "canonical_statement": "用户喜欢喝可乐",
                    "is_active": True,
                    "confidence": 0.78,
                },
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=24,
                owner_id="u-1",
                owner_type="user",
                entry_type="user_fact",
                fact_kind="preference",
                entry_key="preference_drink_coke",
                canonical_text="用户喜欢喝可乐",
                summary="用户喜欢喝可乐",
                status="active",
                entry_data={
                    "key": "preference_drink_coke",
                    "semantic_key": "preference_drink_coke",
                    "value": "可乐",
                    "fact_kind": "preference",
                    "canonical_statement": "用户喜欢喝可乐",
                    "is_active": True,
                    "confidence": 0.86,
                },
                created_at=now,
                updated_at=now,
            ),
        ]
        self.user_relations = []
        self.projection_updates = []
        self.projection_upserts = []
        self.entry_updates = []
        self.relation_updates = []

    def list_projections(self, *, owner_type, **kwargs):
        return list(self.user_views if owner_type == "user" else self.skill_proposals)

    def list_entries(self, *, owner_type, **kwargs):
        return list(self.user_entries if owner_type == "user" else [])

    def list_relations(self, **kwargs):
        return list(self.user_relations)

    def resolve_entry_identity(self, *, entry=None, row=None, payload=None):
        return SessionLedgerRepository.resolve_entry_identity(
            entry=entry,
            row=row,
            payload=payload,
        )

    def resolve_view_identity(self, *, projection=None, row=None, payload=None):
        return SessionLedgerRepository.resolve_view_identity(
            projection=projection,
            row=row,
            payload=payload,
        )

    def resolve_relation_identity(self, *, relation=None, row=None, payload=None):
        return SessionLedgerRepository.resolve_relation_identity(
            relation=relation,
            row=row,
            payload=payload,
        )

    def get_projection(self, *, owner_type, owner_id, projection_type, projection_key):
        rows = self.user_views if owner_type == "user" else self.skill_proposals
        for row in rows:
            row_type = getattr(row, "view_type", None) or "skill_proposal"
            row_key = getattr(row, "view_key", None) or getattr(row, "proposal_key", None)
            if (
                str(row.owner_id) == str(owner_id)
                and str(row_type) == str(projection_type)
                and str(row_key) == str(projection_key)
            ):
                return row
        return None

    def update_projection(self, projection_id, status=None, payload=None, projection_key=None):
        self.projection_updates.append((projection_id, status, payload, projection_key))
        for row in self.user_views + self.skill_proposals:
            if row.id != projection_id:
                continue
            if status is not None:
                row.status = status
            if projection_key is not None and hasattr(row, "view_key"):
                row.view_key = projection_key
            if payload is not None:
                if hasattr(row, "view_data"):
                    row.view_data = payload
                else:
                    row.proposal_payload = payload
            break

    def upsert_projection(self, *, projection, source_session_id=None):
        del source_session_id
        self.projection_upserts.append(projection)
        existing = self.get_projection(
            owner_type=projection.owner_type,
            owner_id=projection.owner_id,
            projection_type=projection.projection_type,
            projection_key=projection.projection_key,
        )
        if existing is not None:
            existing.title = projection.title
            existing.summary = projection.summary
            existing.status = projection.status
            existing.view_data = dict(projection.payload or {})
            return existing.id

        next_id = max((row.id for row in self.user_views), default=0) + 1
        self.user_views.append(
            SimpleNamespace(
                id=next_id,
                owner_id=projection.owner_id,
                owner_type=projection.owner_type,
                view_type=projection.projection_type,
                view_key=projection.projection_key,
                title=projection.title,
                summary=projection.summary,
                details=projection.details,
                status=projection.status,
                view_data=dict(projection.payload or {}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return next_id

    def update_entry(self, entry_id, status=None, payload=None, entry_key=None):
        self.entry_updates.append((entry_id, status, payload, entry_key))
        for row in self.user_entries:
            if row.id != entry_id:
                continue
            if status is not None:
                row.status = status
            if entry_key is not None:
                row.entry_key = entry_key
            if payload is not None:
                row.entry_data = payload
            break

    def update_relation(self, relation_id, status=None, payload=None, relation_key=None):
        self.relation_updates.append((relation_id, status, payload, relation_key))


def test_run_maintenance_consolidates_status_and_supersedes_duplicates() -> None:
    repo = _RepoStub()
    service = ProjectionMaintenanceService(session_repository=repo)

    result = service.run_maintenance(dry_run=False)
    payload = service.to_dict(result)

    assert payload["consolidation"]["episode_view_upserts"] == 1
    assert payload["consolidation"]["user_status_updates"] == 3
    assert payload["consolidation"]["user_entry_status_updates"] == 2
    assert payload["consolidation"]["user_view_identity_rewrites"] >= 1
    assert payload["consolidation"]["user_entry_identity_rewrites"] >= 2
    assert payload["consolidation"]["skill_proposal_duplicate_supersedes"] == 1
    assert payload["consolidation"]["user_duplicate_entry_supersedes"] == 1

    assert any(update[0] == 1 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(update[0] == 2 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(update[0] == 3 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(
        update[0] == 4 and update[3] != "preference_drink_coke"
        for update in repo.projection_updates
    )
    assert any(update[0] == 11 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(update[0] == 20 and update[1] == "superseded" for update in repo.entry_updates)
    assert any(
        update[0] == 21 and update[3] != "life_event_move_abc123" for update in repo.entry_updates
    )
    assert any(update[0] == 22 and update[1] == "superseded" for update in repo.entry_updates)
    assert any(update[0] == 23 and update[1] == "superseded" for update in repo.entry_updates)
    assert any(
        update[0] == 24 and update[3] != "preference_drink_coke" for update in repo.entry_updates
    )
    assert any(item.projection_type == "episode" for item in repo.projection_upserts)


def test_episode_projection_inherits_inactive_source_entry_status() -> None:
    repo = _RepoStub()
    repo.user_entries = [
        SimpleNamespace(
            id=30,
            owner_id="u-1",
            owner_type="user",
            entry_type="user_fact",
            fact_kind="event",
            entry_key="event_dining_superseded",
            canonical_text="2026年3月17日用户将和小陈一起去吃汉堡",
            summary="2026年3月17日用户将和小陈一起去吃汉堡",
            event_time="2026-03-17",
            topic="聚餐",
            location="汉堡店",
            confidence=0.9,
            importance=0.8,
            status="superseded",
            entry_data={
                "key": "event_dining_superseded",
                "semantic_key": "event_dining_with_xiaochen_2026_03_17",
                "value": "用户将与小陈一起去吃汉堡",
                "fact_kind": "event",
                "canonical_statement": "2026年3月17日用户将和小陈一起去吃汉堡",
                "event_time": "2026-03-17",
                "topic": "聚餐",
                "location": "汉堡店",
                "persons": ["小陈"],
                "confidence": 0.9,
                "importance": 0.8,
                "is_active": False,
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    repo.user_views = []

    service = ProjectionMaintenanceService(session_repository=repo)

    service.run_maintenance(dry_run=False)

    episode_upsert = next(
        item for item in repo.projection_upserts if item.projection_type == "episode"
    )
    assert episode_upsert.status == "superseded"
    assert episode_upsert.payload["is_active"] is False
