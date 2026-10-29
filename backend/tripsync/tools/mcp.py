"""Minimal synchronous client for MCP servers over Streamable HTTP (JSON-RPC 2.0).
Enough for one-shot tool calls such as Kiwi.com's public flight search; no SDK needed."""
import json
import logging

import requests

from ..config import USER_AGENT, offline
from ..http import OfflineError, session

log = logging.getLogger(__name__)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
           "User-Agent": USER_AGENT}
PROTOCOL = "2025-03-26"


class MCPError(RuntimeError):
    pass


def _rpc_result(resp: requests.Response, rpc_id: int) -> dict:
    """The reply is either plain JSON or an SSE stream of `data:` lines."""
    if resp.headers.get("content-type", "").startswith("text/event-stream"):
        msgs = [json.loads(line[5:]) for line in resp.text.splitlines() if line.startswith("data:")]
    else:
        msgs = [resp.json()]
    for m in msgs:
        if m.get("id") == rpc_id:
            if "error" in m:
                raise MCPError(m["error"].get("message", str(m["error"])))
            return m["result"]
    raise MCPError("no reply from MCP server")


def call_tool(url: str, name: str, arguments: dict, timeout: float = 45) -> dict:
    """Initialise a session, call one tool and return its structured result (or parsed text content)."""
    if offline():
        raise OfflineError(url)
    init = requests.post(url, headers=HEADERS, timeout=15, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                   "clientInfo": {"name": "tripsync", "version": "0.1"}}})
    init.raise_for_status()
    _rpc_result(init, 1)
    headers = dict(HEADERS)
    if sid := init.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = sid
        requests.post(url, headers=headers, timeout=10,
                      json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    # Tool calls go through the disk cache so repeated searches don't hit the server.
    resp = session().post(url, headers=headers, timeout=timeout, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    resp.raise_for_status()
    result = _rpc_result(resp, 2)
    if result.get("isError"):
        raise MCPError(" ".join(c.get("text", "") for c in result.get("content", []))[:300])
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    return json.loads(text)
