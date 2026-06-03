#!/usr/bin/env python3
"""
HTTP/SSE Transport Wrapper for vector-indexer-mcp (local PostgreSQL backend).

Endpoints:
  GET  /sse        - SSE connection for MCP protocol
  POST /messages/  - Message endpoint for MCP protocol
  GET  /health     - Health check endpoint

Usage:
  python sse_server_local.py
  python sse_server_local.py --port 5577
  MCP_SSE_PORT=5577 python sse_server_local.py
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import uvicorn  # noqa: E402
from mcp.server.sse import SseServerTransport  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.responses import JSONResponse, Response  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vector-indexer-mcp-sse-local")


class _SseResponse(Response):
    async def __call__(self, scope, receive, send):
        pass  # SSE transport already handled the response


def create_app():
    """Create Starlette app wrapping server_local's MCP server."""
    # Import the local server module to get its Server instance
    from src.server_local import server as mcp_server

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        logger.info(
            f"SSE connection from {request.client.host if request.client else 'unknown'}"
        )
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )
        return _SseResponse()

    async def health(request):
        return JSONResponse(
            {
                "status": "healthy",
                "server": "vector-indexer-mcp",
                "transport": "sse-local",
            }
        )

    routes = [
        Route("/health", endpoint=health, methods=["GET"]),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    ]

    return Starlette(routes=routes, middleware=middleware)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", "-p", type=int, default=int(os.environ.get("MCP_SSE_PORT", "5577"))
    )
    parser.add_argument("--host", default=os.environ.get("MCP_SSE_HOST", "127.0.0.1"))
    args = parser.parse_args()

    logger.info("Initializing vector-indexer-mcp (local PostgreSQL)...")
    app = create_app()
    logger.info(f"Starting SSE server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
