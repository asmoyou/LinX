"""Cleanup helpers for reset-era user-memory rows and legacy collection retirement."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.connection import get_db_session
from database.models import (
    SessionLedger,
    SessionLedgerEvent,
    SkillProposal,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryView,
)

logger = logging.getLogger(__name__)
LEGACY_USER_MEMORY_ENTRIES_COLLECTION = "user_memory_entries"


def prepare_user_memory_rows_for_user_deletion(
    session: Any,
    *,
    user_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete reset-era user-memory rows for one user inside an existing DB transaction."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {
            "user_id": normalized_user_id,
            "entry_ids": [],
            "session_ids": [],
            "session_ledgers": 0,
            "session_events": 0,
            "memory_entries": 0,
            "memory_links": 0,
            "memory_views": 0,
            "skill_proposals": 0,
            "deleted": False,
        }

    entry_ids = [
        str(row[0])
        for row in session.query(UserMemoryEntry.id)
        .filter(UserMemoryEntry.user_id == normalized_user_id)
        .all()
        if row[0] is not None
    ]
    session_ids = [
        int(row[0])
        for row in session.query(SessionLedger.id)
        .filter(SessionLedger.user_id == normalized_user_id)
        .all()
        if row[0] is not None
    ]

    session_events = 0
    if session_ids:
        session_events = (
            session.query(SessionLedgerEvent)
            .filter(SessionLedgerEvent.session_ledger_id.in_(session_ids))
            .count()
        )

    memory_links = (
        session.query(UserMemoryLink).filter(UserMemoryLink.user_id == normalized_user_id).count()
    )
    memory_views = (
        session.query(UserMemoryView).filter(UserMemoryView.user_id == normalized_user_id).count()
    )
    skill_proposals = (
        session.query(SkillProposal).filter(SkillProposal.user_id == normalized_user_id).count()
    )

    if not dry_run:
        (
            session.query(UserMemoryLink)
            .filter(UserMemoryLink.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(UserMemoryEntry)
            .filter(UserMemoryEntry.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(UserMemoryView)
            .filter(UserMemoryView.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(SkillProposal)
            .filter(SkillProposal.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(SessionLedger)
            .filter(SessionLedger.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        session.flush()

    return {
        "user_id": normalized_user_id,
        "entry_ids": entry_ids,
        "session_ids": session_ids,
        "session_ledgers": len(session_ids),
        "session_events": session_events,
        "memory_entries": len(entry_ids),
        "memory_links": memory_links,
        "memory_views": memory_views,
        "skill_proposals": skill_proposals,
        "deleted": not dry_run,
    }


def drop_legacy_user_memory_vector_collection(
    *,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Drop the unused legacy Milvus collection if it still exists."""

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    try:
        exists = bool(connection.collection_exists(LEGACY_USER_MEMORY_ENTRIES_COLLECTION))
    except Exception as exc:
        logger.warning(
            "Failed to inspect legacy user-memory Milvus collection",
            extra={"collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION, "error": str(exc)},
        )
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": None,
            "dropped": False,
            "dry_run": dry_run,
            "error": str(exc),
        }

    if not exists:
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": False,
            "dropped": False,
            "dry_run": dry_run,
            "error": None,
        }

    if dry_run:
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": False,
            "dry_run": True,
            "error": None,
        }

    try:
        connection.drop_collection(LEGACY_USER_MEMORY_ENTRIES_COLLECTION)
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": True,
            "dry_run": False,
            "error": None,
        }
    except Exception as exc:
        logger.warning(
            "Failed to drop legacy user-memory Milvus collection",
            extra={"collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION, "error": str(exc)},
        )
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": False,
            "dry_run": False,
            "error": str(exc),
        }
