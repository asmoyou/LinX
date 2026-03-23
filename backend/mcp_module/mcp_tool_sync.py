"""MCP tool discovery and sync.

Connects to an MCP server, discovers its tools, and creates/updates
Skill records so they appear in the skill library.
"""

import logging
import re
import uuid as uuid_mod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from uuid import UUID

from mcp.types import Tool

from database.connection import get_db_session
from database.models import McpServer, Skill, SkillRevision
from mcp_module.mcp_client import MCPConnectionManager, get_mcp_connection_manager
from mcp_module.mcp_registry import MCPServerRegistry, get_mcp_server_registry
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9_-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


@dataclass
class SyncResult:
    """Result of a tool sync operation."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    total_tools: int = 0
    errors: List[str] = field(default_factory=list)


class MCPToolSync:
    """Discovers tools from MCP servers and syncs them as Skill records."""

    def __init__(
        self,
        connection_manager: Optional[MCPConnectionManager] = None,
        registry: Optional[MCPServerRegistry] = None,
    ):
        self._conn_manager = connection_manager or get_mcp_connection_manager()
        self._registry = registry or get_mcp_server_registry()

    async def sync_server_tools(self, server_id: UUID) -> SyncResult:
        """Connect to an MCP server and sync its tools into the skill library.

        Steps:
        1. Connect to the server
        2. Discover all tools via list_tools()
        3. Upsert Skill records for each tool
        4. Deactivate skills whose tools no longer exist
        5. Update server sync metadata
        """
        result = SyncResult()

        server = self._registry.get_server(server_id)
        if not server:
            result.errors.append(f"MCP server {server_id} not found")
            return result

        self._registry.update_status(server_id, "syncing")

        try:
            await self._conn_manager.get_or_connect(server_id)
            tools = await self._conn_manager.list_tools(server_id)
            result.total_tools = len(tools)

            logger.info(
                "Discovered %d tools from MCP server %s", len(tools), server.name
            )

            # Build set of discovered tool names for removal detection
            discovered_tool_names: Set[str] = set()

            with get_db_session() as session:
                for tool in tools:
                    try:
                        skill_slug = f"mcp_{_slugify(server.name)}_{_slugify(tool.name)}"
                        discovered_tool_names.add(skill_slug)

                        existing = (
                            session.query(Skill)
                            .filter(
                                Skill.mcp_server_id == server_id,
                                Skill.skill_slug == skill_slug,
                            )
                            .one_or_none()
                        )

                        interface_def = self._convert_input_schema(tool)

                        if existing:
                            # Update existing skill
                            existing.display_name = tool.name
                            existing.description = tool.description or f"MCP tool: {tool.name}"
                            existing.interface_definition = interface_def
                            existing.skill_metadata = {
                                "mcp_tool_name": tool.name,
                                "mcp_server_name": server.name,
                                "mcp_server_id": str(server_id),
                            }
                            existing.is_active = True
                            self._upsert_revision(session, existing, tool)
                            result.updated += 1
                        else:
                            # Create new skill
                            skill = Skill(
                                skill_id=uuid_mod.uuid4(),
                                skill_slug=skill_slug,
                                display_name=tool.name,
                                description=tool.description or f"MCP tool: {tool.name}",
                                skill_type="mcp_tool",
                                source_kind="mcp",
                                artifact_kind="tool",
                                runtime_mode="tool",
                                lifecycle_state="active",
                                storage_type="inline",
                                interface_definition=interface_def,
                                mcp_server_id=server_id,
                                is_active=True,
                                access_level="public",
                                skill_metadata={
                                    "mcp_tool_name": tool.name,
                                    "mcp_server_name": server.name,
                                    "mcp_server_id": str(server_id),
                                },
                            )
                            session.add(skill)
                            session.flush()
                            self._create_revision(session, skill, tool)
                            result.added += 1

                    except Exception as e:
                        logger.error("Failed to sync tool %s: %s", tool.name, e)
                        result.errors.append(f"Tool {tool.name}: {e}")

                # Deactivate skills whose tools no longer exist on the server
                existing_skills = (
                    session.query(Skill)
                    .filter(
                        Skill.mcp_server_id == server_id,
                        Skill.is_active.is_(True),
                    )
                    .all()
                )
                for skill in existing_skills:
                    if skill.skill_slug not in discovered_tool_names:
                        skill.is_active = False
                        result.removed += 1
                        logger.info("Deactivated removed MCP tool: %s", skill.skill_slug)

                session.commit()

            # Update server sync info
            self._registry.update_sync_info(server_id, result.total_tools)
            self._registry.update_status(server_id, "connected")

            logger.info(
                "Sync complete for %s: added=%d, updated=%d, removed=%d",
                server.name,
                result.added,
                result.updated,
                result.removed,
            )
            return result

        except Exception as e:
            error_msg = f"Sync failed for server {server.name}: {e}"
            logger.error(error_msg, exc_info=True)
            self._registry.update_status(server_id, "error", str(e))
            result.errors.append(error_msg)
            return result

    def _convert_input_schema(self, tool: Tool) -> dict:
        """Convert MCP tool inputSchema to LinX interface_definition format."""
        input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
        if not isinstance(input_schema, dict):
            input_schema = {}

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        inputs: Dict[str, str] = {}
        for name, prop in properties.items():
            json_type = prop.get("type", "string")
            inputs[name] = json_type

        return {
            "inputs": inputs,
            "outputs": {"result": "string"},
            "required_inputs": required,
            "mcp_input_schema": input_schema,
            "mcp_tool_name": tool.name,
        }

    def _create_revision(self, session, skill: Skill, tool: Tool) -> SkillRevision:
        """Create the initial revision for a synced MCP tool."""
        revision = SkillRevision(
            revision_id=uuid_mod.uuid4(),
            skill_id=skill.skill_id,
            version="1.0.0",
            review_state="approved",
            instruction_md=None,
            tool_code=None,
            interface_definition=skill.interface_definition,
            artifact_storage_kind="inline",
            artifact_ref=None,
            manifest=None,
            config=None,
            search_document=f"{tool.name} {tool.description or ''}".strip(),
        )
        session.add(revision)
        session.flush()
        skill.active_revision_id = revision.revision_id
        return revision

    def _upsert_revision(self, session, skill: Skill, tool: Tool) -> None:
        """Update the active revision for an existing MCP tool skill."""
        revision = (
            session.query(SkillRevision)
            .filter(SkillRevision.revision_id == skill.active_revision_id)
            .one_or_none()
        )
        if revision:
            revision.interface_definition = skill.interface_definition
            revision.search_document = f"{tool.name} {tool.description or ''}".strip()
        else:
            self._create_revision(session, skill, tool)


_tool_sync: Optional[MCPToolSync] = None


def get_mcp_tool_sync() -> MCPToolSync:
    """Get the singleton MCPToolSync instance."""
    global _tool_sync
    if _tool_sync is None:
        _tool_sync = MCPToolSync()
    return _tool_sync
