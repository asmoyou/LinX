"""LangChain BaseTool wrapper for MCP tools.

Wraps an MCP tool so it can be bound to an LLM via LangChain's
bind_tools() mechanism, routing execution through the MCP client.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)


def _json_type_to_python(json_type: str) -> type:
    """Map JSON Schema type strings to Python types."""
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


def create_args_schema_from_mcp(
    tool_name: str,
    input_schema: dict,
) -> Type[BaseModel]:
    """Create a Pydantic model from an MCP tool's inputSchema.

    Args:
        tool_name: Name of the MCP tool (used for model name)
        input_schema: JSON Schema from the MCP tool definition

    Returns:
        A dynamically created Pydantic BaseModel class
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    fields: Dict[str, Any] = {}
    for name, prop in properties.items():
        py_type = _json_type_to_python(prop.get("type", "string"))
        description = prop.get("description", "")

        if name in required:
            fields[name] = (py_type, Field(description=description))
        else:
            fields[name] = (Optional[py_type], Field(default=None, description=description))

    if not fields:
        # Fallback: accept arbitrary keyword arguments
        fields["input"] = (Optional[str], Field(default=None, description="Input for the tool"))

    # Sanitize model name
    safe_name = "".join(c if c.isalnum() else "_" for c in tool_name)
    model_name = f"MCP_{safe_name}_Args"

    return create_model(model_name, **fields)


class MCPToolWrapper(BaseTool):
    """LangChain BaseTool wrapper that routes execution to an MCP server.

    When the LLM invokes this tool, the call is forwarded to the
    corresponding MCP server via the MCPConnectionManager.
    """

    name: str = ""
    description: str = ""
    args_schema: Optional[Type[BaseModel]] = None

    # MCP-specific fields stored as plain attributes
    mcp_server_id: Optional[str] = None
    mcp_tool_name: str = ""

    def _run(self, **kwargs: Any) -> str:
        """Synchronous execution — delegates to async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._arun(**kwargs))
                return future.result()
        else:
            return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        """Async execution through the MCP client."""
        from mcp_module.mcp_client import get_mcp_connection_manager

        if not self.mcp_server_id:
            return "Error: MCP server ID not configured"

        try:
            manager = get_mcp_connection_manager()
            result = await manager.call_tool(UUID(self.mcp_server_id), self.mcp_tool_name, kwargs)

            # result may be dict (HTTP client) or CallToolResult (SDK)
            if isinstance(result, dict):
                content_items = result.get("content", [])
                content_parts = [
                    item.get("text", "") for item in content_items
                    if isinstance(item, dict) and item.get("text")
                ]
                is_error = result.get("isError", False)
            else:
                content_parts = [
                    item.text for item in getattr(result, "content", [])
                    if hasattr(item, "text")
                ]
                is_error = getattr(result, "isError", False)

            output = "\n".join(content_parts) if content_parts else "Tool returned no content"

            if is_error:
                return f"MCP tool error: {output}"

            return output

        except Exception as e:
            logger.error(
                "MCP tool execution failed: %s/%s: %s",
                self.mcp_server_id,
                self.mcp_tool_name,
                e,
                exc_info=True,
            )
            return f"Error calling MCP tool {self.mcp_tool_name}: {e}"
