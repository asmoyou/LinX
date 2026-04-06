"""WebSocket Endpoint for Real-Time Updates.

References:
- Requirements 13, 15: Task Flow Visualization and API
- Task 2.1.10: Implement WebSocket endpoint for real-time updates
- Task 4.5: Task Flow Visualization
"""

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Store active WebSocket connections by user_id
active_connections: Dict[Any, Set[WebSocket]] = {}

# Store task flow subscriptions: task_id -> set of websockets
task_flow_subscriptions: Dict[UUID, Set[WebSocket]] = {}

offline_message_queue: DefaultDict[str, List[dict[str, Any]]] = defaultdict(list)


class ConnectionManager:
    """Minimal connection manager used by legacy websocket helpers and tests."""

    def __init__(self):
        self.active_connections = active_connections

    async def connect(self, websocket: WebSocket, user_id: UUID | str) -> None:
        self.active_connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: UUID | str) -> None:
        _remove_active_connection(user_id, websocket)

    async def send_personal_message(self, message: dict[str, Any], user_id: UUID | str) -> None:
        connections = list(self.active_connections.get(user_id, set()))
        stale_connections: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale_connections.append(connection)
        for connection in stale_connections:
            await self.disconnect(connection, user_id)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

def _get_connection_manager() -> ConnectionManager:
    return ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    """Compatibility websocket endpoint used by tests and older callers."""

    manager = _get_connection_manager()
    await websocket.accept()
    await manager.connect(websocket, user_id)
    try:
        payload = await websocket.receive_text()
        if payload == "ping":
            await send_heartbeat(websocket, user_id)
    finally:
        await manager.disconnect(websocket, user_id)


async def send_task_update(
    user_id: UUID | str,
    task_id: UUID | str,
    status: str,
    progress: Optional[int] = None,
) -> None:
    await _get_connection_manager().send_personal_message(
        {
            "type": "task_update",
            "task_id": str(task_id),
            "status": status,
            "progress": progress,
        },
        user_id,
    )


async def broadcast_agent_status(
    agent_id: UUID | str,
    status: str,
    current_task: Optional[str] = None,
) -> None:
    await _get_connection_manager().broadcast(
        {
            "type": "agent_status",
            "agent_id": str(agent_id),
            "status": status,
            "current_task": current_task,
        }
    )


async def stream_logs(user_id: UUID | str, task_id: UUID | str, log_entry: dict[str, Any]) -> None:
    await _get_connection_manager().send_personal_message(
        {
            "type": "task_log",
            "task_id": str(task_id),
            "log_entry": log_entry,
        },
        user_id,
    )


async def handle_client_message(websocket: WebSocket, user_id: UUID | str) -> dict[str, Any]:
    message = await websocket.receive_json()
    if message.get("type") == "subscribe":
        response = {
            "type": "subscription_confirmed",
            "channel": message.get("channel"),
            "user_id": str(user_id),
        }
    else:
        response = {
            "type": "message_received",
            "user_id": str(user_id),
        }
    await websocket.send_json(response)
    return response


async def send_heartbeat(websocket: WebSocket, user_id: UUID | str) -> None:
    await websocket.send_json({"type": "heartbeat", "user_id": str(user_id)})


async def queue_message_for_offline_user(user_id: UUID | str, message: dict[str, Any]) -> None:
    offline_message_queue[str(user_id)].append(message)


def _remove_active_connection(user_id: Any, websocket: WebSocket) -> None:
    connections = active_connections.get(user_id)
    if not connections:
        return
    connections.discard(websocket)
    if not connections:
        active_connections.pop(user_id, None)


def _remove_task_flow_subscription(task_id: UUID, websocket: WebSocket) -> None:
    subscriptions = task_flow_subscriptions.get(task_id)
    if not subscriptions:
        return
    subscriptions.discard(websocket)
    if not subscriptions:
        task_flow_subscriptions.pop(task_id, None)


@router.websocket("/tasks")
async def websocket_task_updates(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates.

    Clients connect to receive real-time updates about task status changes.
    """
    await websocket.accept()

    # TODO: Authenticate WebSocket connection
    # TODO: Extract user_id from token
    user_id = "anonymous"

    # Add connection to active connections
    if user_id not in active_connections:
        active_connections[user_id] = set()
    active_connections[user_id].add(websocket)

    logger.info("WebSocket connected", extra={"user_id": user_id, "endpoint": "tasks"})

    try:
        while True:
            # Keep connection alive and receive messages
            data = await websocket.receive_text()

            # Echo back for now (placeholder)
            await websocket.send_json({"type": "echo", "data": data})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"user_id": user_id, "endpoint": "tasks"})
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={"user_id": user_id, "endpoint": "tasks", "error": str(e)},
        )
    finally:
        _remove_active_connection(user_id, websocket)


async def broadcast_task_update(user_id: str, task_update: dict):
    """Broadcast task update to all user's WebSocket connections.

    Args:
        user_id: User ID to broadcast to
        task_update: Task update data
    """
    connections = active_connections.get(user_id)
    if not connections:
        return

    stale_connections = []
    for connection in list(connections):
        try:
            await connection.send_json(task_update)
        except Exception as e:
            logger.error(
                f"Failed to send WebSocket message: {str(e)}", extra={"user_id": user_id}
            )
            stale_connections.append(connection)

    for connection in stale_connections:
        _remove_active_connection(user_id, connection)


@router.websocket("/tasks/{task_id}/flow")
async def websocket_task_flow(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task flow visualization.

    Clients connect to receive real-time updates about task flow changes.

    Args:
        websocket: WebSocket connection
        task_id: Root task ID to subscribe to
    """
    await websocket.accept()

    # TODO: Authenticate WebSocket connection
    # TODO: Extract user_id from token
    user_id = "anonymous"

    task_uuid: Optional[UUID] = None
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        await websocket.send_json({"type": "error", "message": "Invalid task ID format"})
        await websocket.close()
        return

    # Add connection to task flow subscriptions
    if task_uuid not in task_flow_subscriptions:
        task_flow_subscriptions[task_uuid] = set()
    task_flow_subscriptions[task_uuid].add(websocket)

    logger.info(
        "WebSocket connected to task flow",
        extra={"user_id": user_id, "task_id": task_id, "endpoint": "task_flow"},
    )

    # Send initial task flow graph
    try:
        from task_manager.task_flow_visualizer import get_task_flow_visualizer

        visualizer = get_task_flow_visualizer()

        # Try to get cached graph or build new one
        graph = visualizer.get_task_flow(task_uuid)
        if not graph:
            # Build graph from database
            # Note: In production, user_id should come from authentication
            from uuid import uuid4

            graph = visualizer.build_task_flow(task_uuid, uuid4())

        if graph:
            await websocket.send_json({"type": "task_flow_initial", "data": graph.to_dict()})
    except Exception as e:
        logger.error(f"Failed to send initial task flow: {str(e)}", extra={"task_id": task_id})
        await websocket.send_json({"type": "error", "message": "Failed to load task flow"})

    try:
        while True:
            # Keep connection alive and receive messages
            data = await websocket.receive_text()

            # Handle client messages (e.g., refresh request)
            if data == "refresh":
                try:
                    from task_manager.task_flow_visualizer import get_task_flow_visualizer

                    visualizer = get_task_flow_visualizer()
                    from uuid import uuid4

                    graph = visualizer.build_task_flow(task_uuid, uuid4())

                    await websocket.send_json({"type": "task_flow_update", "data": graph.to_dict()})
                except Exception as e:
                    logger.error(
                        f"Failed to refresh task flow: {str(e)}", extra={"task_id": task_id}
                    )

    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected from task flow", extra={"user_id": user_id, "task_id": task_id}
        )
    except Exception as e:
        logger.error(
            "WebSocket task flow error",
            extra={"user_id": user_id, "task_id": task_id, "error": str(e)},
        )
    finally:
        if task_uuid is not None:
            _remove_task_flow_subscription(task_uuid, websocket)
            # TODO: When task flow caching is fully implemented, clear cached graphs when no
            # active subscribers remain for a task.


async def broadcast_task_flow_update(task_id: UUID, update_type: str, data: dict):
    """Broadcast task flow update to all subscribed WebSocket connections.

    Args:
        task_id: Root task ID
        update_type: Type of update (node_update, relationship_added, etc.)
        data: Update data
    """
    if task_id in task_flow_subscriptions:
        message = {"type": update_type, "data": data, "timestamp": data.get("timestamp") or None}

        for connection in list(task_flow_subscriptions[task_id]):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(
                    f"Failed to send task flow update: {str(e)}", extra={"task_id": str(task_id)}
                )
                # Remove dead connection
                task_flow_subscriptions[task_id].discard(connection)


# ------------------------------------------------------------------
# Mission WebSocket
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Mission WebSocket (legacy runtime path removed)
# ------------------------------------------------------------------


def broadcast_mission_event(mission_id: UUID, event: dict) -> None:
    """Legacy no-op kept only so historical mission-system callers do not crash."""
    del mission_id, event
    return
