#!/usr/bin/env python3
"""
Vector Indexer MCP Server - Phase 4

Provides semantic and lexical search tools over the vector-indexed codebase.

Tools:
- search_semantic: Vector similarity search
- search_lexical: Full-text search (FTS)
- search_hybrid: Combined semantic + lexical search
- index_status: Get index health statistics
- reindex_path: Force reindex a file/directory
- get_file_chunks: View chunks for a specific file
- search_similar_files: Find files similar to a given file
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Any, Optional, List
import asyncio

# Add project root to sys.path so utils/ package is findable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Embedding generation (lazy-loaded)
_embedder = None

from utils.response import ResponseEnvelope, ErrorCodes
from utils.env_config import get_env, require_env
from utils.db_client import get_db_client

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP server
app = Server("vector-indexer-mcp")

# Database client (supports both Supabase and local PostgreSQL)
db = get_db_client()
logger.info(f"Database client initialized: {type(db).__name__}")

# Embedding model configuration
EMBEDDING_MODEL = get_env("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")


def get_embedder():
    """Lazy-load the embedding model on first query."""
    global _embedder
    if _embedder is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedder


def format_response(response: dict) -> list[types.TextContent]:
    """Format response as MCP TextContent."""
    return [types.TextContent(type="text", text=json.dumps(response, indent=2))]


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max_length characters."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """List all available tools."""
    return [
        # Semantic Search
        types.Tool(
            name="search_semantic",
            description="Vector similarity search using semantic embeddings. Best for finding conceptually similar code/docs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text (will be embedded)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "minimum": 1,
                        "maximum": 100
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity threshold 0.0-1.0 (default: 0.5)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file extensions (e.g., ['.py', '.md'])"
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file paths (e.g., ['/srv/latvian_mcp'])"
                    }
                },
                "required": ["query"]
            }
        ),

        # Lexical Search (FTS)
        types.Tool(
            name="search_lexical",
            description="Full-text search using PostgreSQL FTS. Best for finding exact keywords or phrases.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text (keywords)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "minimum": 1,
                        "maximum": 100
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file extensions (e.g., ['.py', '.md'])"
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file paths (e.g., ['/srv/latvian_mcp'])"
                    }
                },
                "required": ["query"]
            }
        ),

        # Hybrid Search
        types.Tool(
            name="search_hybrid",
            description="Combined semantic + lexical search. Best for balanced results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "minimum": 1,
                        "maximum": 100
                    },
                    "alpha": {
                        "type": "number",
                        "description": "Blend factor: 0.0=pure FTS, 1.0=pure vector, 0.5=balanced (default: 0.5)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file extensions (e.g., ['.py', '.md'])"
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by file paths (e.g., ['/srv/latvian_mcp'])"
                    }
                },
                "required": ["query"]
            }
        ),

        # Index Status
        types.Tool(
            name="index_status",
            description="Get index health statistics and metrics",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # Reindex Path
        types.Tool(
            name="reindex_path",
            description="Force reindex a file or directory. Queues files for processing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path to reindex"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Recursively index directory contents (default: true)"
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force reindex even if unchanged (default: false)"
                    }
                },
                "required": ["path"]
            }
        ),

        # Get File Chunks
        types.Tool(
            name="get_file_chunks",
            description="View all indexed chunks for a specific file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute file path"
                    }
                },
                "required": ["file_path"]
            }
        ),

        # Search Similar Files
        types.Tool(
            name="search_similar_files",
            description="Find files similar to a given file using average embedding comparison",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Reference file path"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "minimum": 1,
                        "maximum": 50
                    }
                },
                "required": ["file_path"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[types.TextContent]:
    """Handle tool calls."""
    try:
        if name == "search_semantic":
            return await handle_search_semantic(arguments)
        elif name == "search_lexical":
            return await handle_search_lexical(arguments)
        elif name == "search_hybrid":
            return await handle_search_hybrid(arguments)
        elif name == "index_status":
            return await handle_index_status(arguments)
        elif name == "reindex_path":
            return await handle_reindex_path(arguments)
        elif name == "get_file_chunks":
            return await handle_get_file_chunks(arguments)
        elif name == "search_similar_files":
            return await handle_search_similar_files(arguments)
        else:
            response = ResponseEnvelope.error(
                ErrorCodes.INVALID_INPUT,
                f"Unknown tool: {name}"
            )
            return format_response(response)
    except Exception as e:
        logger.error(f"Error handling tool call {name}: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Internal error: {str(e)}"
        )
        return format_response(response)


async def handle_search_semantic(args: dict) -> list[types.TextContent]:
    """Vector similarity search."""
    query = args.get("query")
    limit = args.get("limit", 20)
    threshold = args.get("threshold", 0.5)
    file_types = args.get("file_types")
    paths = args.get("paths")

    if not query:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "query is required"
        )
        return format_response(response)

    try:
        # Generate query embedding
        embedder = get_embedder()
        query_embedding = embedder.encode(query, normalize_embeddings=True).tolist()

        # Call database function (schema-qualified)
        result = db.rpc(
            "vectors.search_vector",
            {
                "query_embedding": query_embedding,
                "result_limit": limit
            }
        )

        chunks = result.data if result.data else []

        # Handle single dict result (Supabase RPC may return different formats)
        if isinstance(chunks, dict):
            chunks = [chunks]

        # Apply filters
        if file_types:
            chunks = [c for c in chunks if any(c['file_path'].endswith(ft) for ft in file_types)]
        if paths:
            chunks = [c for c in chunks if any(c['file_path'].startswith(p) for p in paths)]

        # Apply threshold filter
        chunks = [c for c in chunks if c.get('similarity', 0) >= threshold]

        # Truncate chunk_text
        for chunk in chunks:
            if 'chunk_text' in chunk:
                chunk['chunk_text'] = truncate_text(chunk['chunk_text'])

        response = ResponseEnvelope.ok(
            message=f"Found {len(chunks)} semantic matches",
            data={
                "chunks": chunks,
                "count": len(chunks),
                "query": query,
                "threshold": threshold
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error in semantic search: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Search failed: {str(e)}"
        )
        return format_response(response)


async def handle_search_lexical(args: dict) -> list[types.TextContent]:
    """Full-text search using FTS."""
    query = args.get("query")
    limit = args.get("limit", 20)
    file_types = args.get("file_types")
    paths = args.get("paths")

    if not query:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "query is required"
        )
        return format_response(response)

    try:
        # Call database function (schema-qualified)
        result = db.rpc(
            "vectors.search_fts",
            {
                "query_text": query,
                "result_limit": limit
            }
        )

        chunks = result.data if result.data else []

        # Apply filters
        if file_types:
            chunks = [c for c in chunks if any(c['file_path'].endswith(ft) for ft in file_types)]
        if paths:
            chunks = [c for c in chunks if any(c['file_path'].startswith(p) for p in paths)]

        # Truncate chunk_text
        for chunk in chunks:
            if 'chunk_text' in chunk:
                chunk['chunk_text'] = truncate_text(chunk['chunk_text'])

        response = ResponseEnvelope.ok(
            message=f"Found {len(chunks)} lexical matches",
            data={
                "chunks": chunks,
                "count": len(chunks),
                "query": query
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error in lexical search: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Search failed: {str(e)}"
        )
        return format_response(response)


async def handle_search_hybrid(args: dict) -> list[types.TextContent]:
    """Hybrid search combining FTS and vector similarity."""
    query = args.get("query")
    limit = args.get("limit", 20)
    alpha = args.get("alpha", 0.5)
    file_types = args.get("file_types")
    paths = args.get("paths")

    if not query:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "query is required"
        )
        return format_response(response)

    try:
        # Generate query embedding
        embedder = get_embedder()
        query_embedding = embedder.encode(query, normalize_embeddings=True).tolist()

        # Call database function (schema-qualified)
        result = db.rpc(
            "vectors.search_hybrid",
            {
                "query_text": query,
                "query_embedding": query_embedding,
                "result_limit": limit,
                "alpha": alpha
            }
        )

        chunks = result.data if result.data else []

        # Apply filters
        if file_types:
            chunks = [c for c in chunks if any(c['file_path'].endswith(ft) for ft in file_types)]
        if paths:
            chunks = [c for c in chunks if any(c['file_path'].startswith(p) for p in paths)]

        # Truncate chunk_text
        for chunk in chunks:
            if 'chunk_text' in chunk:
                chunk['chunk_text'] = truncate_text(chunk['chunk_text'])

        response = ResponseEnvelope.ok(
            message=f"Found {len(chunks)} hybrid matches (alpha={alpha})",
            data={
                "chunks": chunks,
                "count": len(chunks),
                "query": query,
                "alpha": alpha
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error in hybrid search: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Search failed: {str(e)}"
        )
        return format_response(response)


async def handle_index_status(args: dict) -> list[types.TextContent]:
    """Get index health statistics."""
    try:
        # Call database function (schema-qualified)
        result = db.rpc("vectors.get_index_health")

        health = result.data if result.data else {}

        response = ResponseEnvelope.ok(
            message="Retrieved index health statistics",
            data={
                "health": health
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error getting index status: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Failed to get index status: {str(e)}"
        )
        return format_response(response)


async def handle_reindex_path(args: dict) -> list[types.TextContent]:
    """Force reindex a file or directory."""
    path = args.get("path")
    recursive = args.get("recursive", True)
    force = args.get("force", False)

    if not path:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "path is required"
        )
        return format_response(response)

    def should_index_file(file_path: str) -> bool:
        """Check if file should be indexed (exclude binary files and problematic directories)."""
        from pathlib import Path as PathLib
        p = PathLib(file_path)

        # Exclude binary file extensions
        binary_extensions = {
            '.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.bin', '.jar', '.class',
            '.o', '.a', '.lib', '.out', '.obj', '.dylib',
            # Images and media
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
            '.mp4', '.avi', '.mov', '.mp3', '.wav', '.flac', '.ogg',
            # Archives
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.rar', '.7z', '.dmg', '.iso'
        }

        if p.suffix.lower() in binary_extensions:
            return False

        # Exclude problematic directory patterns
        path_parts = p.parts
        excluded_dirs = {
            '__pycache__', '.cache', 'node_modules', '.git', '.svn', '.hg',
            '.venv', 'venv', '.env', 'env', '.tox', '.pytest_cache',
            'build', 'dist', 'target', 'bin', 'obj'
        }

        for part in path_parts:
            if part in excluded_dirs:
                return False

        # Include only specific file extensions (match watcher.yaml config)
        include_extensions = {
            '.py', '.md', '.txt', '.json', '.yaml', '.yml', '.sql',
            '.sh', '.toml', '.ini', '.cfg', '.conf'
        }

        if p.suffix.lower() not in include_extensions:
            return False

        return True

    try:
        from pathlib import Path as PathLib
        p = PathLib(path)

        files_to_queue = []

        if p.is_file():
            if should_index_file(str(p.absolute())):
                files_to_queue.append(str(p.absolute()))
        elif p.is_dir():
            if recursive:
                # Get all files recursively
                for item in p.rglob("*"):
                    if item.is_file() and should_index_file(str(item.absolute())):
                        files_to_queue.append(str(item.absolute()))
            else:
                # Get files in directory only
                for item in p.glob("*"):
                    if item.is_file() and should_index_file(str(item.absolute())):
                        files_to_queue.append(str(item.absolute()))
        else:
            response = ResponseEnvelope.error(
                ErrorCodes.NOT_FOUND,
                f"Path not found: {path}"
            )
            return format_response(response)

        # Queue files for indexing
        queued_count = 0
        for file_path in files_to_queue:
            try:
                # Check if file is already indexed (unless force=True)
                if not force:
                    existing = db.table("vectors.file_metadata").select("id").eq("file_path", file_path).execute()
                    if existing.data:
                        logger.info(f"Skipping already-indexed file: {file_path}")
                        continue

                # Remove any existing queue entries for this file
                db.table("vectors.index_queue").delete().eq("file_path", file_path).execute()

                # Insert into queue
                db.table("vectors.index_queue").insert({
                    "file_path": file_path,
                    "event": "modify" if force else "create",
                    "priority": 3  # Medium priority
                }).execute()
                queued_count += 1

            except Exception as e:
                logger.warning(f"Failed to queue {file_path}: {e}")

        response = ResponseEnvelope.ok(
            message=f"Queued {queued_count} file(s) for reindexing",
            data={
                "queued_count": queued_count,
                "total_files": len(files_to_queue),
                "path": path,
                "recursive": recursive,
                "force": force
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error reindexing path: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.INTERNAL_ERROR,
            f"Reindex failed: {str(e)}"
        )
        return format_response(response)


async def handle_get_file_chunks(args: dict) -> list[types.TextContent]:
    """View all indexed chunks for a specific file."""
    file_path = args.get("file_path")

    if not file_path:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "file_path is required"
        )
        return format_response(response)

    try:
        # Get file metadata
        file_result = db.table("vectors.file_metadata").select("*").eq("file_path", file_path).execute()

        if not file_result.data:
            response = ResponseEnvelope.error(
                ErrorCodes.NOT_FOUND,
                f"File not indexed: {file_path}"
            )
            return format_response(response)

        file_meta = file_result.data[0]
        file_id = file_meta['id']

        # Get chunks
        chunks_result = db.table("vectors.file_chunks").select("*").eq("file_id", file_id).order("chunk_index").execute()

        chunks = chunks_result.data if chunks_result.data else []

        # Truncate chunk_text
        for chunk in chunks:
            if 'chunk_text' in chunk:
                chunk['chunk_text'] = truncate_text(chunk['chunk_text'])

        response = ResponseEnvelope.ok(
            message=f"Retrieved {len(chunks)} chunk(s) for {file_path}",
            data={
                "file_metadata": file_meta,
                "chunks": chunks,
                "chunk_count": len(chunks)
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error getting file chunks: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Failed to get file chunks: {str(e)}"
        )
        return format_response(response)


async def handle_search_similar_files(args: dict) -> list[types.TextContent]:
    """Find files similar to a given file using average embedding comparison."""
    file_path = args.get("file_path")
    limit = args.get("limit", 10)

    if not file_path:
        response = ResponseEnvelope.error(
            ErrorCodes.INVALID_INPUT,
            "file_path is required"
        )
        return format_response(response)

    try:
        # Get file metadata
        file_result = db.table("vectors.file_metadata").select("id").eq("file_path", file_path).execute()

        if not file_result.data:
            response = ResponseEnvelope.error(
                ErrorCodes.NOT_FOUND,
                f"File not indexed: {file_path}"
            )
            return format_response(response)

        file_id = file_result.data[0]['id']

        # Get all chunk IDs for this file first
        chunks_result = db.table("vectors.file_chunks").select("id").eq("file_id", file_id).execute()

        if not chunks_result.data:
            response = ResponseEnvelope.error(
                ErrorCodes.NOT_FOUND,
                f"No chunks found for file: {file_path}"
            )
            return format_response(response)

        chunk_ids = [c['id'] for c in chunks_result.data]

        # Get all embeddings for these chunks
        embeddings_result = db.table("vectors.file_embeddings").select("embedding").in_("chunk_id", chunk_ids).execute()

        if not embeddings_result.data:
            response = ResponseEnvelope.error(
                ErrorCodes.NOT_FOUND,
                f"No embeddings found for file: {file_path}"
            )
            return format_response(response)

        # Calculate average embedding
        import numpy as np
        embeddings = [e['embedding'] for e in embeddings_result.data]
        avg_embedding = np.mean(embeddings, axis=0).tolist()

        # Search for similar files using average embedding
        # Use raw SQL query to find similar files (excluding the source file)
        from postgrest import APIError

        # Get similar chunks
        similar_result = db.rpc(
            "vectors.search_vector",
            {
                "query_embedding": avg_embedding,
                "result_limit": limit * 10  # Get more to filter by file
            }
        )

        chunks = similar_result.data if similar_result.data else []

        # Group by file and calculate average similarity
        files_similarity = {}
        for chunk in chunks:
            fp = chunk['file_path']
            if fp == file_path:  # Skip source file
                continue

            if fp not in files_similarity:
                files_similarity[fp] = []
            files_similarity[fp].append(chunk.get('similarity', 0))

        # Calculate average similarity per file
        similar_files = []
        for fp, similarities in files_similarity.items():
            avg_sim = sum(similarities) / len(similarities)
            similar_files.append({
                "file_path": fp,
                "similarity": round(avg_sim, 4),
                "chunk_count": len(similarities)
            })

        # Sort by similarity and limit
        similar_files.sort(key=lambda x: x['similarity'], reverse=True)
        similar_files = similar_files[:limit]

        response = ResponseEnvelope.ok(
            message=f"Found {len(similar_files)} similar file(s)",
            data={
                "reference_file": file_path,
                "similar_files": similar_files,
                "count": len(similar_files)
            }
        )
        return format_response(response)

    except Exception as e:
        logger.error(f"Error finding similar files: {e}", exc_info=True)
        response = ResponseEnvelope.error(
            ErrorCodes.EXTERNAL_SERVICE_ERROR,
            f"Failed to find similar files: {str(e)}"
        )
        return format_response(response)


def main():
    """Run the MCP server."""
    import asyncio

    logger.info("Starting Vector Indexer MCP server...")

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
