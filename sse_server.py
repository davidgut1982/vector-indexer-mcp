#!/usr/bin/env python3
"""
HTTP/SSE Transport Wrapper for vector-indexer-mcp

Exposes the vector-indexer-mcp MCP server over HTTP/SSE for use with
the ContextForge gateway and other SSE-compatible clients.

Endpoints:
  GET  /sse        - SSE connection for MCP protocol
  POST /messages/  - Message endpoint for MCP protocol
  GET  /health     - Health check endpoint
  GET  /info       - Server info endpoint

Usage:
  python sse_server.py                    # Default port 5573
  python sse_server.py --port 5573        # Custom port
  MCP_SSE_PORT=5573 python sse_server.py  # Via environment
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path so utils/ package is findable
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Add src directory to path for server module import
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse, Response
from mcp.server.sse import SseServerTransport

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vector-indexer-mcp-sse")


class _SseResponse(Response):
    """
    No-op Response for SSE endpoints.

    The SSE transport handles the response directly via ASGI send callback.
    This response class satisfies Starlette's expectation of a return value
    without actually sending anything (since SSE already handled it).
    """
    async def __call__(self, scope, receive, send):
        # Do nothing - SSE transport already sent the response
        pass


def initialize_mcp_server():
    """
    Initialize the vector-indexer-mcp server with Supabase configuration.

    Returns the configured MCP server instance ready for use.
    """
    # Import after path setup
    from utils.env_config import require_env, get_env

    # Import the server module
    import server as vector_indexer_server

    # Initialize Supabase configuration
    vector_indexer_server.SUPABASE_URL = require_env("SUPABASE_URL")
    vector_indexer_server.SUPABASE_KEY = require_env("SUPABASE_KEY")
    vector_indexer_server.supabase = vector_indexer_server.create_client(
        vector_indexer_server.SUPABASE_URL,
        vector_indexer_server.SUPABASE_KEY
    )

    logger.info(f"Initialized Supabase connection to {vector_indexer_server.SUPABASE_URL}")

    return vector_indexer_server.app


def create_app(mcp_server):
    """Create Starlette app with MCP SSE endpoints and CORS support."""

    # Initialize SSE transport with message endpoint
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connection for MCP protocol."""
        logger.info(f"SSE connection from {request.client.host if request.client else 'unknown'}")

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

        # Return no-op response - SSE transport already sent everything
        return _SseResponse()

    async def health(request):
        """Health check endpoint."""
        return JSONResponse({
            "status": "healthy",
            "server": "vector-indexer-mcp",
            "transport": "sse"
        })

    async def info(request):
        """Server info endpoint."""
        return JSONResponse({
            "name": "vector-indexer-mcp",
            "version": "1.0.0",
            "transport": "sse",
            "protocol": "mcp",
            "endpoints": {
                "sse": "/sse",
                "messages": "/messages/",
                "health": "/health",
                "info": "/info"
            },
            "tools": [
                "search_semantic",
                "search_lexical",
                "search_hybrid",
                "index_status",
                "reindex_path",
                "get_file_chunks",
                "search_similar_files"
            ]
        })

    # Define routes
    routes = [
        Route("/health", endpoint=health, methods=["GET"]),
        Route("/info", endpoint=info, methods=["GET"]),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    # Configure CORS middleware for Docker network and gateway access
    # ContextForge gateway connects from Docker network at 172.17.0.1
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:*",
                "http://127.0.0.1:*",
                "http://172.17.0.1:*",  # Docker bridge network
                "http://172.17.0.*:*",  # Docker containers
                "*"  # Allow all origins for development
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    ]

    return Starlette(routes=routes, middleware=middleware)


def main():
    """Run the vector-indexer-mcp SSE server."""
    parser = argparse.ArgumentParser(
        description="HTTP/SSE wrapper for vector-indexer-mcp"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("MCP_SSE_PORT", "5573")),
        help="HTTP port to listen on (default: 5573)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_SSE_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    # Initialize the MCP server with Supabase
    logger.info("Initializing vector-indexer-mcp server...")
    mcp_server = initialize_mcp_server()

    # Create and run the HTTP app
    app = create_app(mcp_server)

    logger.info(f"Starting vector-indexer-mcp SSE server on {args.host}:{args.port}")
    logger.info(f"Health check: http://{args.host}:{args.port}/health")
    logger.info(f"SSE endpoint: http://{args.host}:{args.port}/sse")
    logger.info(f"Messages endpoint: http://{args.host}:{args.port}/messages/")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
