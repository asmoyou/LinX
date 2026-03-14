from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.projection_maintenance_service import ProjectionMaintenanceService


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
            )
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
        ]
        self.projection_updates = []
        self.projection_upserts = []
        self.entry_updates = []

    def list_projections(self, *, owner_type, **kwargs):
        return list(self.user_views if owner_type == "user" else self.skill_proposals)

    def list_entries(self, *, owner_type, **kwargs):
        return list(self.user_entries if owner_type == "user" else [])

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

    def update_projection(self, projection_id, status=None, payload=None):
        self.projection_updates.append((projection_id, status, payload))
        for row in self.user_views + self.skill_proposals:
            if row.id != projection_id:
                continue
            if status is not None:
                row.status = status
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

    def update_entry(self, entry_id, status=None, payload=None):
        self.entry_updates.append((entry_id, status, payload))
        for row in self.user_entries:
            if row.id != entry_id:
                continue
            if status is not None:
                row.status = status
            if payload is not None:
                row.entry_data = payload
            break


def test_run_maintenance_consolidates_status_and_supersedes_duplicates() -> None:
    repo = _RepoStub()
    service = ProjectionMaintenanceService(session_repository=repo)

    result = service.run_maintenance(dry_run=False)
    payload = service.to_dict(result)

    assert payload["consolidation"]["episode_view_upserts"] == 1
    assert payload["consolidation"]["user_status_updates"] == 1
    assert payload["consolidation"]["user_entry_status_updates"] == 1
    assert payload["consolidation"]["skill_proposal_duplicate_supersedes"] == 1

    assert any(update[0] == 1 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(update[0] == 11 and update[1] == "superseded" for update in repo.projection_updates)
    assert any(update[0] == 20 and update[1] == "superseded" for update in repo.entry_updates)
    assert any(item.projection_type == "episode" for item in repo.projection_upserts)
