"""MCP client connection manager.

- **stdio**: Uses MCP SDK ``ClientSessionGroup`` on a background event loop.
- **sse / streamable_http**: Uses ``HttpMcpClient`` (plain ``requests`` POST),
  bypassing the SDK's broken async transport that crashes with ExceptionGroup.
  This mirrors cherry-studio's ``StreamableHTTPClientTransport`` approach.
"""

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.config import get_config

logger = logging.getLogger(__name__)


def _format_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_format_exception(s) for s in exc.exceptions) or repr(exc)
    return str(exc) or type(exc).__name__


# ---------------------------------------------------------------------------
# Background event loop for stdio (MCP SDK needs anyio isolation)
# ---------------------------------------------------------------------------

_mcp_loop: Optional[asyncio.AbstractEventLoop] = None
_mcp_thread: Optional[threading.Thread] = None


def _get_mcp_event_loop() -> asyncio.AbstractEventLoop:
    global _mcp_loop, _mcp_thread
    if _mcp_loop is not None and _mcp_loop.is_running():
        return _mcp_loop
    _mcp_loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(_mcp_loop)
        _mcp_loop.run_forever()

    _mcp_thread = threading.Thread(target=_run, daemon=True, name="mcp-event-loop")
    _mcp_thread.start()
    return _mcp_loop


def _run_in_mcp_loop(coro, timeout: float = 120):
    loop = _get_mcp_event_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class McpServerConfig:
    server_id: UUID
    name: str
    transport_type: str  # "stdio" | "sse" | "streamable_http"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# MCPConnection
# ---------------------------------------------------------------------------

class MCPConnection:
    """Wraps either a stdio SDK session or an HTTP client."""

    def __init__(self, config: McpServerConfig):
        self.config = config
        self.status: str = "disconnected"
        self.error: Optional[str] = None

        # stdio backend
        self._group = None       # ClientSessionGroup
        self._session = None     # ClientSession

        # http backend
        self._http_client = None  # HttpMcpClient

    @property
    def _is_http(self) -> bool:
        return self.config.transport_type in ("sse", "streamable_http")

    # -- connect --------------------------------------------------------

    def connect(self) -> None:
        """Connect (blocking, called from any thread)."""
        try:
            if self._is_http:
                self._connect_http()
            else:
                self._connect_stdio()
            self.status = "connected"
            self.error = None
        except BaseException as e:
            self.status = "error"
            self.error = _format_exception(e)
            self.disconnect()
            raise ConnectionError(f"Failed to connect to {self.config.name}: {self.error}") from e

    def _connect_http(self) -> None:
        from mcp_module.http_client import HttpMcpClient

        if not self.config.url:
            raise ValueError("HTTP transport requires a URL")
        self._http_client = HttpMcpClient(
            url=self.config.url,
            headers=self.config.headers,
        )
        self._http_client.connect()
        logger.info("Connected to MCP server %s via HTTP (%s)", self.config.name, self.config.url)

    def _connect_stdio(self) -> None:
        from mcp import ClientSessionGroup, StdioServerParameters

        if not self.config.command:
            raise ValueError("stdio transport requires a command")

        async def _do():
            self._group = ClientSessionGroup()
            env = dict(self.config.env_vars or {})
            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=env if env else None,
            )
            self._session = await self._group.connect_to_server(params)

        _run_in_mcp_loop(_do())
        logger.info("Connected to MCP server %s via stdio", self.config.name)

    # -- disconnect -----------------------------------------------------

    def disconnect(self) -> None:
        if self._http_client:
            self._http_client.close()
            self._http_client = None
        if self._session and self._group:
            try:
                _run_in_mcp_loop(self._group.disconnect_from_server(self._session))
            except BaseException as e:
                logger.debug("Suppress stdio disconnect error: %s", e)
            self._session = None
            self._group = None
        self.status = "disconnected"

    # -- list_tools / call_tool -----------------------------------------

    def list_tools(self):
        if self._is_http:
            return self._http_client.list_tools()
        # stdio
        return _run_in_mcp_loop(self._session.list_tools()).tools

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None):
        if self._is_http:
            return self._http_client.call_tool(name, arguments)
        # stdio
        return _run_in_mcp_loop(self._session.call_tool(name, arguments=arguments or {}))


# ---------------------------------------------------------------------------
# MCPConnectionManager
# ---------------------------------------------------------------------------

class MCPConnectionManager:
    def __init__(self):
        self._connections: Dict[UUID, MCPConnection] = {}
        self._configs: Dict[UUID, McpServerConfig] = {}
        cfg = (get_config().get_section("mcp") or {}) if get_config() else {}
        self._max_retries = int(cfg.get("max_retries", 3))

    def register_server(self, config: McpServerConfig) -> None:
        self._configs[config.server_id] = config

    async def get_or_connect(self, server_id: UUID) -> MCPConnection:
        conn = self._connections.get(server_id)
        if conn and conn.status == "connected":
            return conn

        config = self._configs.get(server_id) or self._load_config_from_db(server_id)
        if not config:
            raise ValueError(f"No MCP server config for {server_id}")
        self._configs[server_id] = config

        conn = MCPConnection(config)
        last_err = None
        for attempt in range(self._max_retries):
            try:
                conn.connect()
                self._connections[server_id] = conn
                return conn
            except BaseException as e:
                last_err = e
                logger.warning("MCP connect %d/%d for %s failed: %s",
                               attempt + 1, self._max_retries, config.name, _format_exception(e))

        raise ConnectionError(
            f"Failed to connect to {config.name} after {self._max_retries} attempts: "
            f"{_format_exception(last_err)}"
        )

    async def list_tools(self, server_id: UUID):
        conn = self._connections.get(server_id)
        if not conn or conn.status != "connected":
            raise RuntimeError(f"MCP server {server_id} not connected")
        return conn.list_tools()

    async def call_tool(self, server_id: UUID, name: str, arguments: Optional[Dict[str, Any]] = None):
        conn = self._connections.get(server_id)
        if not conn or conn.status != "connected":
            raise RuntimeError(f"MCP server {server_id} not connected")
        return conn.call_tool(name, arguments)

    def _load_config_from_db(self, server_id: UUID) -> Optional[McpServerConfig]:
        from database.connection import get_db_session
        from database.models import McpServer

        with get_db_session() as session:
            srv = session.query(McpServer).filter(
                McpServer.server_id == server_id, McpServer.is_active.is_(True)
            ).one_or_none()
            if not srv:
                return None
            return McpServerConfig(
                server_id=srv.server_id, name=srv.name,
                transport_type=srv.transport_type, command=srv.command,
                args=srv.args, url=srv.url, headers=srv.headers, env_vars=srv.env_vars,
            )

    async def disconnect(self, server_id: UUID) -> None:
        conn = self._connections.pop(server_id, None)
        if conn:
            conn.disconnect()

    async def disconnect_all(self) -> None:
        for sid in list(self._connections):
            await self.disconnect(sid)

    def get_connection_status(self, server_id: UUID) -> str:
        conn = self._connections.get(server_id)
        return conn.status if conn else "disconnected"


_connection_manager: Optional[MCPConnectionManager] = None


def get_mcp_connection_manager() -> MCPConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = MCPConnectionManager()
    return _connection_manager
