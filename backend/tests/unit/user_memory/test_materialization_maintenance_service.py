from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.materialization_maintenance_service import (
    MaterializationMaintenanceService,
)


class _RepoStub:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.user_materializations = [
            SimpleNamespace(
                id=1,
                owner_id="u-1",
                owner_type="user",
                materialization_type="user_profile",
                materialization_key="response_style",
                title="User preference: response_style",
                status="active",
                materialized_data={"is_active": False, "confidence": 0.7},
                created_at=now,
                updated_at=now,
            )
        ]
        self.agent_materializations = [
            SimpleNamespace(
                id=10,
                owner_id="a-1",
                owner_type="agent",
                materialization_type="agent_experience",
                materialization_key="pdf-path-a",
                title="Stable PDF delivery",
                status="active",
                materialized_data={
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
                materialization_type="agent_experience",
                materialization_key="pdf-path-b",
                title="Stable PDF delivery",
                status="pending_review",
                materialized_data={
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
                entry_key="response_style",
                summary="concise",
                status="active",
                entry_data={"key": "response_style", "is_active": False, "confidence": 0.7},
                created_at=now,
                updated_at=now,
            )
        ]
        self.agent_entries = [
            SimpleNamespace(
                id=30,
                owner_id="a-1",
                owner_type="agent",
                entry_type="agent_skill_candidate",
                entry_key="pdf-path-a",
                summary="Stable PDF delivery",
                status="active",
                entry_data={
                    "goal": "Stable PDF delivery",
                    "successful_path": ["inspect", "convert", "verify"],
                    "confidence": 0.9,
                    "review_status": "published",
                },
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=31,
                owner_id="a-1",
                owner_type="agent",
                entry_type="agent_skill_candidate",
                entry_key="pdf-path-b",
                summary="Stable PDF delivery",
                status="pending_review",
                entry_data={
                    "goal": "Stable PDF delivery",
                    "successful_path": ["inspect", "convert", "verify"],
                    "confidence": 0.5,
                    "review_status": "pending",
                },
                created_at=now,
                updated_at=now,
            ),
        ]
        self.materialization_updates = []
        self.entry_updates = []

    def list_materializations(self, *, owner_type, **kwargs):
        return list(
            self.user_materializations if owner_type == "user" else self.agent_materializations
        )

    def list_entries(self, *, owner_type, **kwargs):
        return list(self.user_entries if owner_type == "user" else self.agent_entries)

    def update_materialization(self, materialization_id, status=None, payload=None):
        self.materialization_updates.append((materialization_id, status, payload))
        for row in self.user_materializations + self.agent_materializations:
            if row.id == materialization_id:
                if status is not None:
                    row.status = status
                if payload is not None:
                    row.materialized_data = payload
                break

    def update_entry(self, entry_id, status=None, payload=None):
        self.entry_updates.append((entry_id, status, payload))
        for row in self.user_entries + self.agent_entries:
            if row.id == entry_id:
                if status is not None:
                    row.status = status
                if payload is not None:
                    row.entry_data = payload
                break


def test_run_maintenance_consolidates_status_and_supersedes_duplicates() -> None:
    repo = _RepoStub()
    service = MaterializationMaintenanceService(session_repository=repo)

    result = service.run_maintenance(dry_run=False)
    payload = service.to_dict(result)

    assert payload["consolidation"]["user_status_updates"] == 1
    assert payload["consolidation"]["user_entry_status_updates"] == 1
    assert payload["consolidation"]["agent_duplicate_supersedes"] == 1
    assert payload["consolidation"]["agent_duplicate_entry_supersedes"] == 1

    assert any(
        update[0] == 1 and update[1] == "superseded" for update in repo.materialization_updates
    )
    assert any(
        update[0] == 11 and update[1] == "superseded" for update in repo.materialization_updates
    )
    assert any(update[0] == 20 and update[1] == "superseded" for update in repo.entry_updates)
    assert any(update[0] == 31 and update[1] == "superseded" for update in repo.entry_updates)
