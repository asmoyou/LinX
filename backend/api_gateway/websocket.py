"""WebSocket Endpoint for Real-Time Updates.

References:
- Requirements 13, 15: Task Flow Visualization and API
- Task 2.1.10: Implement WebSocket endpoint for real-time updates
- Task 4.5: Task Flow Visualization
"""

from typing import Dict, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Store active WebSocket connections by user_id
active_connections: Dict[str, Set[WebSocket]] = {}

# Store task flow subscriptions: task_id -> set of websockets
task_flow_subscriptions: Dict[UUID, Set[WebSocket]] = {}

# Store mission subscriptions: mission_id -> set of websockets
mission_subscriptions: Dict[UUID, Set[WebSocket]] = {}

# Store global mission subscriptions (all mission events)
mission_global_subscriptions: Set[WebSocket] = set()


def _remove_active_connection(user_id: str, websocket: WebSocket) -> None:
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


def _remove_mission_subscription(mission_id: UUID, websocket: WebSocket) -> None:
    subscriptions = mission_subscriptions.get(mission_id)
    if not subscriptions:
        return
    subscriptions.discard(websocket)
    if not subscriptions:
        mission_subscriptions.pop(mission_id, None)


def _remove_global_mission_subscription(websocket: WebSocket) -> None:
    mission_global_subscriptions.discard(websocket)


@router.websocket("/missions")
async def websocket_all_mission_updates(websocket: WebSocket):
    """WebSocket endpoint for global mission event streaming."""
    await websocket.accept()
    mission_global_subscriptions.add(websocket)

    logger.info("WebSocket connected to global missions stream", extra={"endpoint": "missions_all"})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected from global missions stream")
    except Exception as e:
        logger.error(
            "WebSocket global missions error",
            extra={"endpoint": "missions_all", "error": str(e)},
        )
    finally:
        _remove_global_mission_subscription(websocket)


@router.websocket("/missions/{mission_id}")
async def websocket_mission_updates(websocket: WebSocket, mission_id: str):
    """WebSocket endpoint for real-time mission event streaming."""
    await websocket.accept()

    mission_uuid: Optional[UUID] = None
    try:
        mission_uuid = UUID(mission_id)
    except ValueError:
        await websocket.send_json({"type": "error", "message": "Invalid mission ID format"})
        await websocket.close()
        return

    if mission_uuid not in mission_subscriptions:
        mission_subscriptions[mission_uuid] = set()
    mission_subscriptions[mission_uuid].add(websocket)

    logger.info(
        "WebSocket connected to mission",
        extra={"mission_id": mission_id, "endpoint": "missions"},
    )

    # Send current mission state as the initial message
    try:
        from mission_system.mission_repository import get_mission

        mission = get_mission(mission_uuid)
        if mission:
            await websocket.send_json({
                "type": "mission_state",
                "data": {
                    "mission_id": str(mission.mission_id),
                    "status": mission.status,
                    "total_tasks": mission.total_tasks,
                    "completed_tasks": mission.completed_tasks,
                    "failed_tasks": mission.failed_tasks,
                },
            })
    except Exception as e:
        logger.error(
            "Failed to send initial mission state",
            extra={"mission_id": mission_id, "error": str(e)},
        )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected from mission",
            extra={"mission_id": mission_id},
        )
    except Exception as e:
        logger.error(
            "WebSocket mission error",
            extra={"mission_id": mission_id, "error": str(e)},
        )
    finally:
        if mission_uuid is not None:
            _remove_mission_subscription(mission_uuid, websocket)


def broadcast_mission_event(mission_id: UUID, event: dict) -> None:
    """Broadcast a mission event to all WebSocket subscribers.

    This is a synchronous helper; it schedules the send on the running
    event loop (safe to call from sync code inside an async app).
    """
    import asyncio

    scoped_subs = mission_subscriptions.get(mission_id, set())
    global_subs = mission_global_subscriptions
    if not scoped_subs and not global_subs:
        return

    payload = dict(event)
    payload.setdefault("mission_id", str(mission_id))
    message = {"type": "mission_event", "data": payload}

    async def _send():
        stale_scoped: Set[WebSocket] = set()
        stale_global: Set[WebSocket] = set()
        for ws in list(scoped_subs):
            try:
                await ws.send_json(message)
            except Exception:
                stale_scoped.add(ws)

        for ws in list(global_subs):
            try:
                await ws.send_json(message)
            except Exception:
                stale_global.add(ws)

        for ws in stale_scoped:
            _remove_mission_subscription(mission_id, ws)
        for ws in stale_global:
            _remove_global_mission_subscription(ws)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send())
    except RuntimeError:
        pass
