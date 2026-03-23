"""Lightweight HTTP MCP client using requests.

Bypasses the MCP Python SDK's broken ``streamablehttp_client`` by making
direct JSON-RPC POST calls — the same approach as cherry-studio's
``StreamableHTTPClientTransport``.

Note: ``httpx`` returns 502 on some MCP servers (HTTP/2 negotiation issue),
so we use ``requests`` which sticks to HTTP/1.1.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests as _requests

logger = logging.getLogger(__name__)


def _parse_sse(text: str) -> Optional[dict]:
    """Extract the first JSON-RPC result from an SSE or plain-JSON response."""
    for line in text.strip().splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


@dataclass
class HttpMcpTool:
    name: str
    description: str
    inputSchema: dict = field(default_factory=dict)


class HttpMcpClient:
    """MCP client that talks Streamable-HTTP via plain POST requests."""

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 60):
        self.url = url
        self._extra_headers = headers or {}
        self._timeout = timeout
        self._session_id: Optional[str] = None
        self._req_id = 0
        self._http = _requests.Session()

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _headers(self) -> dict:
        h: Dict[str, str] = {
            "Accept": "application/json, text/event-stream",
            **self._extra_headers,
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _post(self, method: str, params: Optional[dict] = None,
              *, is_notification: bool = False) -> Optional[dict]:
        body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not is_notification:
            body["id"] = self._next_id()
        if params is not None:
            body["params"] = params

        resp = self._http.post(
            self.url, json=body, headers=self._headers(), timeout=self._timeout,
        )

        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid

        if resp.status_code == 202:
            return None

        # Session expired / server restarted — auto-reconnect once
        if resp.status_code in (404, 502) and not is_notification and self._session_id:
            logger.info("MCP session expired (%d), reconnecting to %s", resp.status_code, self.url)
            self._session_id = None
            self.connect()
            # Retry the request with fresh session
            body["id"] = self._next_id()
            resp = self._http.post(
                self.url, json=body, headers=self._headers(), timeout=self._timeout,
            )
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self._session_id = sid
            if resp.status_code == 202:
                return None

        resp.raise_for_status()

        data = _parse_sse(resp.text)
        if data and "error" in data:
            err = data["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        return data

    # ------------------------------------------------------------------
    # Public API (matches MCPConnection interface)
    # ------------------------------------------------------------------

    def connect(self) -> dict:
        result = self._post("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "LinX", "version": "1.0"},
        })
        self._post("notifications/initialized", is_notification=True)
        logger.info("HTTP MCP connected to %s (session=%s)", self.url, self._session_id)
        return result or {}

    def list_tools(self) -> List[HttpMcpTool]:
        data = self._post("tools/list", {})
        if not data:
            return []
        return [
            HttpMcpTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in data.get("result", {}).get("tools", [])
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> dict:
        data = self._post("tools/call", {"name": name, "arguments": arguments or {}})
        return data.get("result", {}) if data else {}

    def ping(self) -> bool:
        try:
            self._post("ping", {})
            return True
        except Exception:
            return False

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass
        self._session_id = None
