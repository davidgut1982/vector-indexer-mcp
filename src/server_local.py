#!/usr/bin/env python3
"""
Vector Indexer MCP Server - Local PostgreSQL backend via asyncpg.

Tools:
- search_semantic: Vector similarity search
- search_lexical: Full-text search (FTS)
- search_hybrid: Combined semantic + lexical search
- index_status: Get index health statistics
- reindex_path: Force reindex a file/directory
- get_file_chunks: View chunks for a specific file
- search_similar_files: Find files similar to a given file
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import asyncpg
import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

CONFIG_PATH = "/home/david/vector-indexer-mcp/config.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

db_cfg = config["database"]
DSN = f"postgresql://{db_cfg['user']}:{db_cfg['password']}@{db_cfg['host']}:{db_cfg['port']}/{db_cfg['name']}"

_pool = None
_embedder = None

INDEXABLE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".sql",
    ".sh",
    ".bash",
    ".ini",
    ".cfg",
}


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DSN)
    return _pool


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        emb_cfg = config.get("embedding", {})
        _embedder = SentenceTransformer(
            emb_cfg.get("model", "paraphrase-multilingual-MiniLM-L12-v2"),
            device=emb_cfg.get("device", "cpu"),
        )
    return _embedder


server = Server("vector-indexer-mcp")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_semantic",
            description="Search indexed files using semantic similarity",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                    "threshold": {"type": "number", "default": 0.5},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_lexical",
            description="Search indexed files using full-text search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_hybrid",
            description="Search using both semantic and lexical methods",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                    "alpha": {"type": "number", "default": 0.5},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="index_status",
            description="Get current index health and statistics",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="reindex_path",
            description="Force reindex of a directory or file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean", "default": True},
                    "force": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="get_file_chunks",
            description="Get all indexed chunks for a specific file",
            inputSchema={
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        ),
        Tool(
            name="search_similar_files",
            description="Find files similar to a given file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["file_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    pool = await get_pool()
    result = await _dispatch(name, arguments, pool)
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def _dispatch(name: str, args: dict, pool) -> Any:
    if name == "search_semantic":
        return await _search_semantic(pool, **args)
    elif name == "search_lexical":
        return await _search_lexical(pool, **args)
    elif name == "search_hybrid":
        return await _search_hybrid(pool, **args)
    elif name == "index_status":
        return await _index_status(pool)
    elif name == "reindex_path":
        return await _reindex_path(pool, **args)
    elif name == "get_file_chunks":
        return await _get_file_chunks(pool, **args)
    elif name == "search_similar_files":
        return await _search_similar_files(pool, **args)
    else:
        return {"error": f"Unknown tool: {name}"}


async def _search_semantic(
    pool, query: str, limit: int = 20, threshold: float = 0.5, paths=None
):
    embedder = get_embedder()
    q_emb = embedder.encode(query).tolist()
    where = "WHERE 1=1"
    params = [str(q_emb), limit]
    if paths:
        conditions = " OR ".join(
            [f"fm.file_path LIKE ${len(params) + i + 1}" for i in range(len(paths))]
        )
        where += f" AND ({conditions})"
        params.extend([f"{p}%" for p in paths])
    sql = f"""
        SELECT fm.file_path, fc.chunk_text, fc.chunk_start_line, fc.chunk_end_line,
               1 - (fe.embedding <=> $1::vector) as similarity
        FROM file_embeddings fe
        JOIN file_chunks fc ON fe.chunk_id = fc.id
        JOIN file_metadata fm ON fc.file_id = fm.id
        {where}
        ORDER BY fe.embedding <=> $1::vector
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows if r["similarity"] >= threshold]


async def _search_lexical(pool, query: str, limit: int = 20, paths=None):
    where = "WHERE fc.fts_vector @@ plainto_tsquery('english', $1)"
    params = [query, limit]
    if paths:
        conditions = " OR ".join(
            [f"fm.file_path LIKE ${len(params) + i + 1}" for i in range(len(paths))]
        )
        where += f" AND ({conditions})"
        params.extend([f"{p}%" for p in paths])
    sql = f"""
        SELECT fm.file_path, fc.chunk_text, fc.chunk_start_line, fc.chunk_end_line,
               ts_rank(fc.fts_vector, plainto_tsquery('english', $1)) as rank
        FROM file_chunks fc
        JOIN file_metadata fm ON fc.file_id = fm.id
        {where}
        ORDER BY rank DESC LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def _search_hybrid(
    pool, query: str, limit: int = 20, alpha: float = 0.5, paths=None
):
    embedder = get_embedder()
    q_emb = embedder.encode(query).tolist()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM search_hybrid($1, $2::vector, $3, $4)",
            query,
            str(q_emb),
            limit,
            alpha,
        )
    results = [dict(r) for r in rows]
    if paths:
        results = [
            r for r in results if any(r["file_path"].startswith(p) for p in paths)
        ]
    return results[:limit]


async def _index_status(pool):
    async with pool.acquire() as conn:
        health = await conn.fetchrow("SELECT get_index_health() as h")
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM index_queue WHERE status='pending'"
        )
        processing = await conn.fetchval(
            "SELECT COUNT(*) FROM index_queue WHERE status='processing'"
        )
    return {
        "health": json.loads(health["h"]) if health else {},
        "queue": {"pending": pending, "processing": processing},
    }


async def _reindex_path(pool, path: str, recursive: bool = True, force: bool = False):
    p = Path(path)
    if not p.exists():
        return {"error": f"Path not found: {path}", "queued": 0}
    if p.is_file():
        files = [str(p)] if p.suffix in INDEXABLE_EXTENSIONS else []
    else:
        glob_fn = p.rglob if recursive else p.glob
        files = [
            str(f)
            for f in glob_fn("*")
            if f.is_file() and f.suffix in INDEXABLE_EXTENSIONS
        ]
    async with pool.acquire() as conn:
        for f in files:
            await conn.execute(
                "INSERT INTO index_queue(file_path, event_type, status) VALUES($1,$2,'pending')",
                f,
                "modify" if force else "create",
            )
    return {"queued": len(files), "path": path}


async def _get_file_chunks(pool, file_path: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT fc.chunk_index, fc.chunk_text, fc.chunk_start_line, fc.chunk_end_line, "
            "fc.token_count, fm.indexed_at "
            "FROM file_chunks fc JOIN file_metadata fm ON fc.file_id=fm.id "
            "WHERE fm.file_path=$1 ORDER BY fc.chunk_index",
            file_path,
        )
    return [dict(r) for r in rows]


async def _search_similar_files(pool, file_path: str, limit: int = 10):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH source_emb AS (
                SELECT fe.embedding
                FROM file_embeddings fe
                JOIN file_chunks fc ON fe.chunk_id = fc.id
                JOIN file_metadata fm ON fc.file_id = fm.id
                WHERE fm.file_path = $1
                LIMIT 1
            )
            SELECT DISTINCT fm.file_path,
                   1 - (fe.embedding <=> (SELECT embedding FROM source_emb)) as similarity
            FROM file_embeddings fe
            JOIN file_chunks fc ON fe.chunk_id = fc.id
            JOIN file_metadata fm ON fc.file_id = fm.id
            WHERE fm.file_path != $1
            ORDER BY similarity DESC LIMIT $2
        """,
            file_path,
            limit,
        )
    return [dict(r) for r in rows]


async def main():
    logging.basicConfig(level=logging.INFO)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
