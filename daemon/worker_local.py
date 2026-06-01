"""Asyncpg-based indexing worker for local PostgreSQL vector search.

Processes index_queue table events and generates embeddings for file content.
"""

import asyncio
import hashlib
import logging
from pathlib import Path

import asyncpg
import yaml

from .chunker_local import TextChunker
from .embedder_local import EmbeddingGenerator

logger = logging.getLogger(__name__)

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

CONFIG_PATH = "/home/david/vector-indexer-mcp/config.yaml"


class IndexingWorker:
    def __init__(self, config_path: str = CONFIG_PATH):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        db = self.config["database"]
        self.dsn = f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['name']}"
        chunk_cfg = self.config.get("chunking", {})
        self.chunker = TextChunker(
            chunk_size_tokens=chunk_cfg.get("chunk_size_tokens", 500),
            overlap_tokens=chunk_cfg.get("overlap_tokens", 50),
        )
        emb_cfg = self.config.get("embedding", {})
        self.embedder = EmbeddingGenerator(
            model_name=emb_cfg.get("model", "paraphrase-multilingual-MiniLM-L12-v2"),
            device=emb_cfg.get("device", "cpu"),
        )
        self.pool = None

    async def start(self):
        self.pool = await asyncpg.create_pool(self.dsn)
        logger.info("IndexingWorker started")
        await self._process_loop()

    async def _process_loop(self):
        poll_ms = self.config.get("queue", {}).get("poll_interval_ms", 500)
        batch_size = self.config.get("queue", {}).get("batch_size", 50)
        while True:
            try:
                await self._process_batch(batch_size)
            except Exception as e:
                logger.error(f"Worker error: {e}")
            await asyncio.sleep(poll_ms / 1000)

    async def _process_batch(self, batch_size: int):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE index_queue SET status='processing' WHERE id IN "
                "(SELECT id FROM index_queue WHERE status='pending' LIMIT $1 FOR UPDATE SKIP LOCKED) "
                "RETURNING id, file_path, event_type",
                batch_size,
            )
            for row in rows:
                try:
                    if row["event_type"] == "delete":
                        await self._handle_delete(conn, row["file_path"])
                    else:
                        await self._handle_upsert(conn, row["file_path"])
                    await conn.execute(
                        "UPDATE index_queue SET status='done', processed_at=NOW() WHERE id=$1",
                        row["id"],
                    )
                except Exception as e:
                    logger.error(f"Failed to index {row['file_path']}: {e}")
                    await conn.execute(
                        "UPDATE index_queue SET status='error' WHERE id=$1", row["id"]
                    )

    async def _handle_upsert(self, conn, file_path: str):
        p = Path(file_path)
        if not p.exists() or p.suffix not in INDEXABLE_EXTENSIONS:
            return
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Cannot read {file_path}: {e}")
            return
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        existing = await conn.fetchrow(
            "SELECT id, file_hash FROM file_metadata WHERE file_path=$1", file_path
        )
        if existing and existing["file_hash"] == file_hash:
            return  # unchanged
        # Upsert metadata
        if existing:
            file_id = existing["id"]
            await conn.execute(
                "UPDATE file_metadata SET file_hash=$1, file_size=$2, updated_at=NOW(), indexed_at=NOW() WHERE id=$3",
                file_hash,
                len(content),
                file_id,
            )
            await conn.execute("DELETE FROM file_chunks WHERE file_id=$1", file_id)
        else:
            file_id = await conn.fetchval(
                "INSERT INTO file_metadata(file_path, file_hash, file_size) VALUES($1,$2,$3) RETURNING id",
                file_path,
                file_hash,
                len(content),
            )
        # Chunk and embed
        chunks = self.chunker.chunk_text(content, file_path)
        if not chunks:
            return
        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_batch(texts)
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = await conn.fetchval(
                "INSERT INTO file_chunks(file_id, chunk_index, chunk_text, chunk_start_line, chunk_end_line, token_count) "
                "VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
                file_id,
                chunk.chunk_index,
                chunk.text,
                chunk.start_line,
                chunk.end_line,
                chunk.token_count,
            )
            await conn.execute(
                "INSERT INTO file_embeddings(chunk_id, embedding) VALUES($1,$2::vector)",
                chunk_id,
                str(embedding),
            )
        logger.info(f"Indexed {file_path}: {len(chunks)} chunks")

    async def _handle_delete(self, conn, file_path: str):
        await conn.execute("DELETE FROM file_metadata WHERE file_path=$1", file_path)
        logger.info(f"Removed from index: {file_path}")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    config = sys.argv[1] if len(sys.argv) > 1 else CONFIG_PATH
    worker = IndexingWorker(config)
    asyncio.run(worker.start())
