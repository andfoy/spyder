# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Spyder MCP server subprocess.

This process exposes a Model Context Protocol endpoint over Streamable HTTP
and forwards tool listings and calls to Spyder through a JSON-RPC bridge on
its stdio (see ``bridge.py``). Running the HTTP server here, instead of in
Spyder, keeps its dependencies and event loop out of the GUI process, just
like it's done for the LSP servers.

Usage::

    SPYDER_MCP_TOKEN=<token> python -m spyder.plugins.mcpserver.server \
        --host 127.0.0.1 --port 8768

The process exits when its stdin is closed, i.e. when Spyder goes away.
"""

# Standard library imports
from __future__ import annotations

import argparse
import asyncio
import hmac
import logging
import os
import sys

# Third-party imports
import mcp.types as types
from mcp.server.lowlevel import Server
import uvicorn

# Local imports
from spyder.plugins.mcpserver.bridge import (
    BridgeError,
    BridgeMethods,
    JsonRpcPeer,
    TOKEN_ENV_VAR,
)

logger = logging.getLogger("spyder.mcpserver")

MCP_PATH = "/mcp"

INSTRUCTIONS = """\
This server controls a running Spyder IDE session.

Use the IPython console tools to run code in the user's live kernels: state
persists between calls, figures are returned as images and also shown in
Spyder's Plots pane. Prefer the variable listing tool over printing large
objects. Code you run is visible to the user in their console.
"""


# ---- Auth
# -----------------------------------------------------------------------------
class BearerTokenMiddleware:
    """ASGI middleware that rejects HTTP requests without the right token."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            received = headers.get(b"authorization", b"")
            if not hmac.compare_digest(received, self.expected):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send(
                    {"type": "http.response.body", "body": b"Unauthorized"}
                )
                return

        await self.app(scope, receive, send)


# ---- Stdio bridge
# -----------------------------------------------------------------------------
def create_stdio_peer() -> JsonRpcPeer:
    """Create a bridge peer over this process' original stdin/stdout."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    # Nothing else may write to the bridge channel, so redirect prints and
    # library output to stderr.
    sys.stdout = sys.stderr

    async def readline() -> bytes:
        # Reading in a thread is portable, unlike connect_read_pipe on
        # Windows
        return await asyncio.to_thread(stdin.readline)

    async def write(data: bytes) -> None:
        stdout.write(data)
        stdout.flush()

    return JsonRpcPeer(readline, write)


# ---- MCP server
# -----------------------------------------------------------------------------
def to_content(item: dict) -> types.ContentBlock:
    """Convert a bridge content dict to an MCP content block."""
    if item.get("type") == "image":
        return types.ImageContent(
            type="image", data=item["data"], mime_type=item["mimeType"]
        )
    return types.TextContent(type="text", text=item.get("text", ""))


def create_mcp_server(peer: JsonRpcPeer) -> Server:
    """Create the MCP server forwarding tools to Spyder through ``peer``."""

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        tools = await peer.request(BridgeMethods.ListTools)
        return types.ListToolsResult(
            tools=[types.Tool.model_validate(tool) for tool in tools]
        )

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        try:
            result = await peer.request(
                BridgeMethods.CallTool,
                {"name": params.name, "arguments": params.arguments or {}},
            )
        except BridgeError as error:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(error))],
                is_error=True,
            )

        return types.CallToolResult(
            content=[to_content(item) for item in result["content"]],
            is_error=result.get("isError", False),
        )

    return Server(
        "spyder",
        title="Spyder IDE",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def serve(host: str, port: int, token: str) -> None:
    peer = create_stdio_peer()
    server = create_mcp_server(peer)

    app = BearerTokenMiddleware(
        server.streamable_http_app(streamable_http_path=MCP_PATH, host=host),
        token,
    )
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", lifespan="on"
    )
    http_server = uvicorn.Server(config)

    http_task = asyncio.create_task(http_server.serve())
    bridge_task = asyncio.create_task(peer.run())

    # Tell Spyder where we are once the socket is listening
    while not http_server.started:
        if http_task.done():
            # Startup failed (e.g. port already in use)
            await http_task
            raise SystemExit(1)
        await asyncio.sleep(0.05)

    await peer.notify(
        BridgeMethods.ServerReady, {"url": f"http://{host}:{port}{MCP_PATH}"}
    )

    # Spyder closed our stdin (or died), so shut down
    await bridge_task
    http_server.should_exit = True
    await http_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Spyder MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    token = os.environ.pop(TOKEN_ENV_VAR, "")
    if not token:
        sys.exit(f"The {TOKEN_ENV_VAR} environment variable must be set")

    asyncio.run(serve(args.host, args.port, token))


if __name__ == "__main__":
    main()
