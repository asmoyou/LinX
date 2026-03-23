"""MCP Servers API router.

CRUD operations for MCP server configurations, tool discovery, and
connection management.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp_servers"])


def _set_mcp_skills_active(server_id: UUID, active: bool) -> int:
    """Enable or disable all skills belonging to an MCP server.

    Returns the number of skills affected.
    """
    from database.connection import get_db_session
    from database.models import Skill

    with get_db_session() as session:
        skills = (
            session.query(Skill)
            .filter(Skill.mcp_server_id == server_id)
            .all()
        )
        count = 0
        for skill in skills:
            if skill.is_active != active:
                skill.is_active = active
                count += 1
        if count:
            session.commit()
            logger.info(
                "%s %d MCP skills for server %s",
                "Enabled" if active else "Disabled", count, server_id,
            )
    return count


# --- Request/Response models ---


class CreateMcpServerRequest(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    transport_type: str = Field(..., pattern="^(stdio|sse|streamable_http)$")
    command: Optional[str] = Field(None, max_length=500)
    args: Optional[List[str]] = None
    url: Optional[str] = Field(None, max_length=500)
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None


class UpdateMcpServerRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    transport_type: Optional[str] = Field(None, pattern="^(stdio|sse|streamable_http)$")
    command: Optional[str] = Field(None, max_length=500)
    args: Optional[List[str]] = None
    url: Optional[str] = Field(None, max_length=500)
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None


class McpServerResponse(BaseModel):
    server_id: str
    name: str
    description: Optional[str] = None
    transport_type: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None
    status: str
    tool_count: int
    last_connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    error_message: Optional[str] = None
    is_active: bool
    created_at: str
    updated_at: str


class SyncResultResponse(BaseModel):
    added: int
    updated: int
    removed: int
    total_tools: int
    errors: List[str]


class ConnectionTestResponse(BaseModel):
    connected: bool
    tool_count: int = 0
    error: Optional[str] = None


# --- Helpers ---


def _server_to_response(server) -> McpServerResponse:
    """Convert a McpServer model to a response dict."""
    return McpServerResponse(
        server_id=str(server.server_id),
        name=server.name,
        description=server.description,
        transport_type=server.transport_type,
        command=server.command,
        args=server.args,
        url=server.url,
        headers=server.headers,
        env_vars=server.env_vars,
        status=server.status or "disconnected",
        tool_count=server.tool_count or 0,
        last_connected_at=server.last_connected_at.isoformat() if server.last_connected_at else None,
        last_sync_at=server.last_sync_at.isoformat() if server.last_sync_at else None,
        error_message=server.error_message,
        is_active=server.is_active,
        created_at=server.created_at.isoformat() if server.created_at else "",
        updated_at=server.updated_at.isoformat() if server.updated_at else "",
    )


# --- Endpoints ---


@router.get("", response_model=List[McpServerResponse])
async def list_mcp_servers(
    active_only: bool = True,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all configured MCP servers."""
    from mcp_module.mcp_registry import get_mcp_server_registry

    registry = get_mcp_server_registry()
    servers = registry.list_servers(active_only=active_only)
    return [_server_to_response(s) for s in servers]


@router.post("", response_model=McpServerResponse, status_code=201)
async def create_mcp_server(
    request: CreateMcpServerRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new MCP server configuration."""
    from mcp_module.mcp_registry import get_mcp_server_registry

    # Validate transport-specific fields
    if request.transport_type == "stdio" and not request.command:
        raise HTTPException(400, "stdio transport requires a command")
    if request.transport_type in ("sse", "streamable_http") and not request.url:
        raise HTTPException(400, f"{request.transport_type} transport requires a url")

    registry = get_mcp_server_registry()
    try:
        server = registry.create_server(
            name=request.name,
            description=request.description,
            transport_type=request.transport_type,
            command=request.command,
            args=request.args,
            url=request.url,
            headers=request.headers,
            env_vars=request.env_vars,
            created_by=current_user.user_id,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, f"MCP server with name '{request.name}' already exists")
        raise HTTPException(500, f"Failed to create MCP server: {e}")

    return _server_to_response(server)


@router.get("/{server_id}", response_model=McpServerResponse)
async def get_mcp_server(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get details of a specific MCP server."""
    from mcp_module.mcp_registry import get_mcp_server_registry

    registry = get_mcp_server_registry()
    server = registry.get_server(server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")
    return _server_to_response(server)


@router.put("/{server_id}", response_model=McpServerResponse)
async def update_mcp_server(
    server_id: UUID,
    request: UpdateMcpServerRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an MCP server configuration."""
    from mcp_module.mcp_registry import get_mcp_server_registry

    registry = get_mcp_server_registry()
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    server = registry.update_server(server_id, **updates)
    if not server:
        raise HTTPException(404, "MCP server not found")
    return _server_to_response(server)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete an MCP server and its synced tools."""
    from mcp_module.mcp_client import get_mcp_connection_manager
    from mcp_module.mcp_registry import get_mcp_server_registry

    # Disconnect first
    manager = get_mcp_connection_manager()
    await manager.disconnect(server_id)

    registry = get_mcp_server_registry()
    deleted = registry.delete_server(server_id)
    if not deleted:
        raise HTTPException(404, "MCP server not found")


@router.post("/{server_id}/connect", response_model=ConnectionTestResponse)
async def test_connection(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Test connection to an MCP server."""
    from mcp_module.mcp_client import McpServerConfig, get_mcp_connection_manager
    from mcp_module.mcp_registry import get_mcp_server_registry

    registry = get_mcp_server_registry()
    server = registry.get_server(server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")

    manager = get_mcp_connection_manager()

    # Register config so connection manager can find it
    config = McpServerConfig(
        server_id=server.server_id,
        name=server.name,
        transport_type=server.transport_type,
        command=server.command,
        args=server.args,
        url=server.url,
        headers=server.headers,
        env_vars=server.env_vars,
    )
    manager.register_server(config)

    try:
        connection = await manager.get_or_connect(server_id)
        tools = await manager.list_tools(server_id)
        registry.update_status(server_id, "connected")
        _set_mcp_skills_active(server_id, True)
        return ConnectionTestResponse(connected=True, tool_count=len(tools))
    except Exception as e:
        logger.error("MCP connect failed for %s: %s", server.name, e, exc_info=True)
        registry.update_status(server_id, "error", str(e))
        _set_mcp_skills_active(server_id, False)
        return ConnectionTestResponse(connected=False, error=str(e))


@router.post("/{server_id}/sync", response_model=SyncResultResponse)
async def sync_tools(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Discover and sync tools from an MCP server into the skill library."""
    from mcp_module.mcp_client import McpServerConfig, get_mcp_connection_manager
    from mcp_module.mcp_registry import get_mcp_server_registry
    from mcp_module.mcp_tool_sync import get_mcp_tool_sync

    registry = get_mcp_server_registry()
    server = registry.get_server(server_id)
    if not server:
        raise HTTPException(404, "MCP server not found")

    # Ensure server config is registered with connection manager
    manager = get_mcp_connection_manager()
    config = McpServerConfig(
        server_id=server.server_id,
        name=server.name,
        transport_type=server.transport_type,
        command=server.command,
        args=server.args,
        url=server.url,
        headers=server.headers,
        env_vars=server.env_vars,
    )
    manager.register_server(config)

    sync = get_mcp_tool_sync()
    result = await sync.sync_server_tools(server_id)

    return SyncResultResponse(
        added=result.added,
        updated=result.updated,
        removed=result.removed,
        total_tools=result.total_tools,
        errors=result.errors,
    )


@router.get("/{server_id}/tools")
async def list_server_tools(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List skills synced from a specific MCP server."""
    from database.connection import get_db_session
    from database.models import Skill

    with get_db_session() as session:
        skills = (
            session.query(Skill)
            .filter(Skill.mcp_server_id == server_id)
            .order_by(Skill.display_name.asc())
            .all()
        )

        return [
            {
                "skill_id": str(s.skill_id),
                "skill_slug": s.skill_slug,
                "display_name": s.display_name,
                "description": s.description,
                "is_active": s.is_active,
                "interface_definition": s.interface_definition,
                "execution_count": s.execution_count,
            }
            for s in skills
        ]


@router.post("/{server_id}/disconnect", status_code=204)
async def disconnect_server(
    server_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Disconnect from an MCP server."""
    from mcp_module.mcp_client import get_mcp_connection_manager
    from mcp_module.mcp_registry import get_mcp_server_registry

    manager = get_mcp_connection_manager()
    await manager.disconnect(server_id)

    registry = get_mcp_server_registry()
    registry.update_status(server_id, "disconnected")

    # Disable all tools from this server
    _set_mcp_skills_active(server_id, False)
