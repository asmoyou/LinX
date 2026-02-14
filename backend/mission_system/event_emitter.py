"""Mission Event Emitter.

Records mission lifecycle events to the database and broadcasts them
over WebSocket for real-time UI updates.
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from database.connection import get_db_session
from database.mission_models import MissionEvent

logger = logging.getLogger(__name__)


class MissionEventEmitter:
    """Persists mission events and relays them to WebSocket subscribers."""

    def emit(
        self,
        mission_id: UUID,
        event_type: str,
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> MissionEvent:
        """Persist a mission event and broadcast it.

        Args:
            mission_id: Owning mission.
            event_type: Structured event name (e.g. ``STATUS_CHANGED``).
            agent_id: Optional agent associated with the event.
            task_id: Optional task associated with the event.
            data: Arbitrary JSON payload.
            message: Human-readable description.

        Returns:
            The created MissionEvent.
        """
        event_id = uuid4()

        with get_db_session() as session:
            event = MissionEvent(
                event_id=event_id,
                mission_id=mission_id,
                event_type=event_type,
                agent_id=agent_id,
                task_id=task_id,
                event_data=data,
                message=message,
            )
            session.add(event)
            session.flush()
            session.expunge(event)

        # Broadcast via WebSocket (fire-and-forget import to avoid
        # circular dependency at module load time)
        try:
            from api_gateway.websocket import broadcast_mission_event

            broadcast_mission_event(
                mission_id=mission_id,
                event={
                    "event_id": str(event_id),
                    "event_type": event_type,
                    "agent_id": str(agent_id) if agent_id else None,
                    "task_id": str(task_id) if task_id else None,
                    "data": data,
                    "message": message,
                },
            )
        except ImportError:
            logger.debug("WebSocket broadcast unavailable; skipping")
        except Exception:
            logger.exception("Failed to broadcast mission event via WebSocket")

        logger.info(
            "Mission event emitted",
            extra={
                "mission_id": str(mission_id),
                "event_type": event_type,
                "event_id": str(event_id),
            },
        )
        return event


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[MissionEventEmitter] = None


def get_event_emitter() -> MissionEventEmitter:
    """Get or create the global MissionEventEmitter singleton."""
    global _instance
    if _instance is None:
        _instance = MissionEventEmitter()
    return _instance
