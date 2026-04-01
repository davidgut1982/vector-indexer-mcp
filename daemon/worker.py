"""Indexing worker for vector search system.

Processes index_queue table events and generates embeddings for file content.
Handles create, modify, delete, and move operations with proper error handling.
"""

import asyncio
import hashlib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to sys.path so utils/ package is findable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db_client import get_db_client

from .chunker import Chunk, TextChunker
from .embedder import EmbeddingGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IndexingWorker:
    """Async worker for processing file indexing operations.

    Monitors index_queue table for pending events and processes them:
    - create/modify: Generate chunks and embeddings
    - delete: Remove file metadata and embeddings
    - move: Update file paths

    Args:
        supabase_url: Supabase project URL
        supabase_key: Supabase service role key
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Overlap tokens between chunks
        batch_size: Number of queue items to process per batch
        embedding_model: Sentence-transformers model name
    """

    def __init__(
        self,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
        batch_size: int = 10,
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    ):
        """Initialize the indexing worker."""
        self.db = get_db_client()
        self.batch_size = batch_size

        # Initialize chunker and embedder
        self.chunker = TextChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        self.embedder = EmbeddingGenerator(model_name=embedding_model)

        logger.info(
            f"IndexingWorker initialized: batch_size={batch_size}, "
            f"max_tokens={max_tokens}, overlap={overlap_tokens}, "
            f"db_backend={type(self.db).__name__}"
        )

    async def run(self, poll_interval: int = 5):
        """Run the worker loop indefinitely.

        Args:
            poll_interval: Seconds to wait between queue checks
        """
        logger.info(f"Starting worker loop (poll_interval={poll_interval}s)")

        while True:
            try:
                await self._process_queue_batch()
                await asyncio.sleep(poll_interval)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)

    async def _process_queue_batch(self):
        """Process a batch of items from the index_queue."""
        # Fetch pending items (schema-qualified)
        response = self.db.table("vectors.index_queue") \
            .select("*") \
            .eq("status", "pending") \
            .order("priority", desc=True) \
            .order("queued_at", desc=False) \
            .limit(self.batch_size) \
            .execute()

        items = response.data

        if not items:
            logger.debug("No pending queue items")
            return

        logger.info(f"Processing {len(items)} queue items")

        for item in items:
            await self._process_queue_item(item)

    async def _process_queue_item(self, item: Dict):
        """Process a single queue item.

        Args:
            item: Queue item dict from index_queue table
        """
        queue_id = item["id"]
        event = item["event"]
        file_path = item["file_path"]

        logger.info(f"Processing: event={event}, file={file_path}")

        try:
            # Mark as processing
            self.db.table("vectors.index_queue") \
                .update({"status": "processing", "processed_at": datetime.utcnow().isoformat()}) \
                .eq("id", queue_id) \
                .execute()

            # Dispatch to event handler
            if event in ["create", "modify"]:
                await self._handle_create_or_modify(file_path, item.get("metadata", {}))
            elif event == "delete":
                await self._handle_delete(file_path)
            elif event == "move":
                # old_path column stores dest_path for move events (set by watcher)
                old_path = item.get("old_path")
                await self._handle_move(old_path, file_path)
            else:
                raise ValueError(f"Unknown event type: {event}")

            # Mark as completed
            self.db.table("vectors.index_queue") \
                .update({"status": "completed"}) \
                .eq("id", queue_id) \
                .execute()

            logger.info(f"Completed: {file_path}")

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}", exc_info=True)

            # Mark as failed with error details
            self.db.table("vectors.index_queue") \
                .update({
                    "status": "failed",
                    "error_message": str(e)
                }) \
                .eq("id", queue_id) \
                .execute()

    async def _handle_create_or_modify(self, file_path: str, metadata: Dict):
        """Handle create or modify event by generating chunks and embeddings.

        Args:
            file_path: Path to the file
            metadata: Additional metadata from queue item
        """
        # Read file content
        content = self._read_file(file_path)

        # Calculate content hash
        content_hash = self._calculate_hash(content)

        # Check if file already exists with same hash
        existing = self.db.table("vectors.file_metadata") \
            .select("id, content_hash") \
            .eq("file_path", file_path) \
            .execute()

        if existing.data:
            existing_record = existing.data[0]
            if existing_record.get("content_hash") == content_hash:
                logger.info(f"File unchanged (hash match): {file_path}")
                return

            # Content changed, delete old chunks and embeddings
            file_id = existing_record["id"]
            await self._delete_file_data(file_id)
        else:
            # New file, create metadata record
            file_size = os.path.getsize(file_path)
            line_count = content.count('\n') + 1
            token_count = self.chunker.count_tokens(content)

            file_metadata = {
                "file_path": file_path,
                "file_size": file_size,
                "content_hash": content_hash,
                "line_count": line_count,
                "token_count": token_count,
                "chunk_count": 0,  # Will update after chunking
                "indexed_at": datetime.utcnow().isoformat()
            }

            result = self.db.table("vectors.file_metadata") \
                .insert(file_metadata) \
                .execute()

            file_id = result.data[0]["id"]

        # Generate chunks
        chunks = self.chunker.chunk_text(content)
        logger.info(f"Generated {len(chunks)} chunks for {file_path}")

        if not chunks:
            logger.warning(f"No chunks generated for {file_path}")
            return

        # Insert chunks and generate embeddings
        await self._insert_chunks_and_embeddings(file_id, chunks)

        # Update chunk count and mark as indexed
        self.db.table("vectors.file_metadata") \
            .update({
                "chunk_count": len(chunks),
                "index_status": "indexed",
                "indexed_at": datetime.utcnow().isoformat()
            }) \
            .eq("id", file_id) \
            .execute()

        # Update index stats
        await self._update_index_stats("files_indexed", 1)
        await self._update_index_stats("chunks_created", len(chunks))

    async def _insert_chunks_and_embeddings(self, file_id: str, chunks: List[Chunk]):
        """Insert chunks and generate embeddings.

        Args:
            file_id: File metadata ID
            chunks: List of Chunk objects
        """
        # Prepare chunk records
        chunk_records = []
        chunk_texts = []

        for chunk in chunks:
            chunk_record = {
                "file_id": file_id,
                "chunk_index": chunk.index,
                "content": chunk.text,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "char_offset": chunk.char_offset,
                "token_count": chunk.token_count
            }
            chunk_records.append(chunk_record)
            chunk_texts.append(chunk.text)

        # Insert chunks
        chunk_result = self.db.table("vectors.file_chunks") \
            .insert(chunk_records) \
            .execute()

        chunk_ids = [record["id"] for record in chunk_result.data]

        # Generate embeddings in batch
        logger.info(f"Generating embeddings for {len(chunk_texts)} chunks")
        embeddings = self.embedder.embed_batch(chunk_texts)

        # Prepare embedding records
        embedding_records = []
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            embedding_record = {
                "chunk_id": chunk_id,
                "embedding": embedding
            }
            embedding_records.append(embedding_record)

        # Insert embeddings
        self.db.table("vectors.file_embeddings") \
            .insert(embedding_records) \
            .execute()

        logger.info(f"Inserted {len(embedding_records)} embeddings")

    async def _handle_delete(self, file_path: str):
        """Handle delete event by removing file metadata and embeddings.

        Args:
            file_path: Path to the deleted file
        """
        # Find file metadata
        result = self.db.table("vectors.file_metadata") \
            .select("id") \
            .eq("file_path", file_path) \
            .execute()

        if not result.data:
            logger.warning(f"File not found in index: {file_path}")
            return

        file_id = result.data[0]["id"]

        # Delete file data (cascades to chunks and embeddings)
        await self._delete_file_data(file_id)

        # Delete metadata record
        self.db.table("vectors.file_metadata") \
            .delete() \
            .eq("id", file_id) \
            .execute()

        logger.info(f"Deleted file from index: {file_path}")

        # Update stats
        await self._update_index_stats("files_deleted", 1)

    async def _handle_move(self, old_path: str, new_path: str):
        """Handle move event by updating file path.

        Args:
            old_path: Original file path
            new_path: New file path
        """
        if not old_path:
            logger.error("Move event missing old_path")
            return

        # Update file path in metadata
        self.db.table("vectors.file_metadata") \
            .update({"file_path": new_path}) \
            .eq("file_path", old_path) \
            .execute()

        logger.info(f"Updated file path: {old_path} -> {new_path}")

    async def _delete_file_data(self, file_id: str):
        """Delete chunks and embeddings for a file.

        Args:
            file_id: File metadata ID
        """
        # Get chunk IDs
        chunks = self.db.table("vectors.file_chunks") \
            .select("id") \
            .eq("file_id", file_id) \
            .execute()

        chunk_ids = [chunk["id"] for chunk in chunks.data]

        if chunk_ids:
            # Delete embeddings
            self.db.table("vectors.file_embeddings") \
                .delete() \
                .in_("chunk_id", chunk_ids) \
                .execute()

            # Delete chunks
            self.db.table("vectors.file_chunks") \
                .delete() \
                .eq("file_id", file_id) \
                .execute()

            logger.debug(f"Deleted {len(chunk_ids)} chunks and embeddings")

    def _read_file(self, file_path: str) -> str:
        """Read file content as text.

        Args:
            file_path: Path to file

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If file is not valid UTF-8
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError as e:
            # Try with error handling
            logger.warning(f"UTF-8 decode error, trying with error handling: {file_path}")
            return path.read_text(encoding='utf-8', errors='replace')

    def _calculate_hash(self, content: str) -> str:
        """Calculate SHA256 hash of content.

        Args:
            content: Text content

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    async def _update_index_stats(self, stat_name: str, increment: int = 1):
        """Update index statistics.

        Args:
            stat_name: Name of statistic to update
            increment: Amount to increment by
        """
        try:
            # Try to update existing stat
            result = self.db.table("vectors.index_stats") \
                .select("value") \
                .eq("stat_name", stat_name) \
                .execute()

            if result.data:
                current_value = result.data[0]["value"]
                new_value = current_value + increment

                self.db.table("vectors.index_stats") \
                    .update({
                        "value": new_value,
                        "updated_at": datetime.utcnow().isoformat()
                    }) \
                    .eq("stat_name", stat_name) \
                    .execute()
            else:
                # Create new stat
                self.db.table("vectors.index_stats") \
                    .insert({
                        "stat_name": stat_name,
                        "value": increment
                    }) \
                    .execute()

        except Exception as e:
            logger.warning(f"Failed to update stat {stat_name}: {e}")


async def main():
    """Main entry point for the indexing worker."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Get configuration from environment
    max_tokens = int(os.getenv("MAX_TOKENS", "500"))
    overlap_tokens = int(os.getenv("OVERLAP_TOKENS", "50"))
    batch_size = int(os.getenv("WORKER_BATCH_SIZE", "10"))
    embedding_model = os.getenv(
        "EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2"
    )

    worker = IndexingWorker(
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        batch_size=batch_size,
        embedding_model=embedding_model
    )

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
