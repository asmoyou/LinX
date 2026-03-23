"""MCP (Model Context Protocol) integration module.

Provides client connectivity, server registry, tool discovery,
and LangChain wrapper for external MCP server tools.

Imports are lazy — submodules are imported on first use to avoid
startup failures when the ``mcp`` package is not installed.
"""

__all__ = [
    "MCPConnectionManager",
    "get_mcp_connection_manager",
    "MCPServerRegistry",
    "get_mcp_server_registry",
    "MCPToolSync",
    "get_mcp_tool_sync",
]
