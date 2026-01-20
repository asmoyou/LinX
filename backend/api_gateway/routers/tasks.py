"""Task Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.8: Create task endpoints
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class CreateTaskRequest(BaseModel):
    """Create task request."""
    goal_text: str


class TaskResponse(BaseModel):
    """Task response model."""
    task_id: str
    goal_text: str
    status: str
    created_by_user_id: str


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: CreateTaskRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Submit a new goal/task."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Requires task manager integration"
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(current_user: CurrentUser = Depends(get_current_user)):
    """List user's tasks."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Requires database integration"
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get task details."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Requires database integration"
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Cancel/delete a task."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Requires database integration"
    )
