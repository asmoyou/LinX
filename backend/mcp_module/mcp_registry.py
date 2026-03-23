"""MCP server registry — CRUD operations on MCP server configurations."""

import logging
from typing import List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import McpServer
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


class MCPServerRegistry:
    """Database-backed registry for MCP server configurations."""

    def list_servers(self, active_only: bool = True) -> List[McpServer]:
        """List all registered MCP servers."""
        with get_db_session() as session:
            query = session.query(McpServer)
            if active_only:
                query = query.filter(McpServer.is_active.is_(True))
            servers = query.order_by(McpServer.created_at.desc()).all()
            session.expunge_all()
            return servers

    def get_server(self, server_id: UUID) -> Optional[McpServer]:
        """Get a single MCP server by ID."""
        with get_db_session() as session:
            server = session.query(McpServer).filter(McpServer.server_id == server_id).one_or_none()
            if server:
                session.expunge(server)
            return server

    def create_server(
        self,
        *,
        name: str,
        transport_type: str,
        description: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[list] = None,
        url: Optional[str] = None,
        headers: Optional[dict] = None,
        env_vars: Optional[dict] = None,
        created_by: Optional[UUID] = None,
    ) -> McpServer:
        """Create a new MCP server configuration."""
        with get_db_session() as session:
            server = McpServer(
                name=name,
                description=description,
                transport_type=transport_type,
                command=command,
                args=args,
                url=url,
                headers=headers,
                env_vars=env_vars,
                created_by=created_by,
            )
            session.add(server)
            session.commit()
            session.refresh(server)
            session.expunge(server)
            logger.info("Created MCP server: %s (%s)", name, transport_type)
            return server

    def update_server(
        self,
        server_id: UUID,
        **kwargs,
    ) -> Optional[McpServer]:
        """Update an MCP server configuration.

        Accepts any combination of: name, description, transport_type, command,
        args, url, headers, env_vars, is_active.
        """
        allowed_fields = {
            "name", "description", "transport_type", "command",
            "args", "url", "headers", "env_vars", "is_active",
        }
        with get_db_session() as session:
            server = session.query(McpServer).filter(McpServer.server_id == server_id).one_or_none()
            if not server:
                return None

            for key, value in kwargs.items():
                if key in allowed_fields:
                    setattr(server, key, value)

            session.commit()
            session.refresh(server)
            session.expunge(server)
            logger.info("Updated MCP server: %s", server_id)
            return server

    def delete_server(self, server_id: UUID) -> bool:
        """Delete an MCP server. Cascades to synced skills."""
        with get_db_session() as session:
            server = session.query(McpServer).filter(McpServer.server_id == server_id).one_or_none()
            if not server:
                return False

            name = server.name
            session.delete(server)
            session.commit()
            logger.info("Deleted MCP server: %s (%s)", name, server_id)
            return True

    def update_status(
        self,
        server_id: UUID,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update the connection status of an MCP server."""
        with get_db_session() as session:
            server = session.query(McpServer).filter(McpServer.server_id == server_id).one_or_none()
            if not server:
                return

            server.status = status
            server.error_message = error_message
            if status == "connected":
                server.last_connected_at = utcnow()
            session.commit()

    def update_sync_info(
        self,
        server_id: UUID,
        tool_count: int,
    ) -> None:
        """Update sync timestamp and tool count after a tool sync."""
        with get_db_session() as session:
            server = session.query(McpServer).filter(McpServer.server_id == server_id).one_or_none()
            if not server:
                return

            server.last_sync_at = utcnow()
            server.tool_count = tool_count
            session.commit()


_registry: Optional[MCPServerRegistry] = None


def get_mcp_server_registry() -> MCPServerRegistry:
    """Get the singleton MCPServerRegistry instance."""
    global _registry
    if _registry is None:
        _registry = MCPServerRegistry()
    return _registry
