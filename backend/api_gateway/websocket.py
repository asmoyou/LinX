"""WebSocket Endpoint for Real-Time Updates.

References:
- Requirements 13, 15: Task Flow Visualization and API
- Task 2.1.10: Implement WebSocket endpoint for real-time updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[str, Set[WebSocket]] = {}


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
    
    logger.info(
        "WebSocket connected",
        extra={"user_id": user_id, "endpoint": "tasks"}
    )
    
    try:
        while True:
            # Keep connection alive and receive messages
            data = await websocket.receive_text()
            
            # Echo back for now (placeholder)
            await websocket.send_json({
                "type": "echo",
                "data": data
            })
            
    except WebSocketDisconnect:
        # Remove connection
        active_connections[user_id].discard(websocket)
        if not active_connections[user_id]:
            del active_connections[user_id]
        
        logger.info(
            "WebSocket disconnected",
            extra={"user_id": user_id, "endpoint": "tasks"}
        )


async def broadcast_task_update(user_id: str, task_update: dict):
    """Broadcast task update to all user's WebSocket connections.
    
    Args:
        user_id: User ID to broadcast to
        task_update: Task update data
    """
    if user_id in active_connections:
        for connection in active_connections[user_id]:
            try:
                await connection.send_json(task_update)
            except Exception as e:
                logger.error(
                    f"Failed to send WebSocket message: {str(e)}",
                    extra={"user_id": user_id}
                )
