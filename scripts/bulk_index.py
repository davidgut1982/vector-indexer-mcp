#!/usr/bin/env python3
"""
Bulk Index Script - Vector Indexer MCP

Indexes all existing files from configured watch directories.
Uses chunker.py and embedder.py to process files and store in PostgreSQL.

Usage:
    python scripts/bulk_index.py --dry-run    # Preview what would be indexed
    python scripts/bulk_index.py --execute    # Actually perform indexing
    python scripts/bulk_index.py --execute --path /specific/path  # Index specific path
"""

import argparse
import sys
import os
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime

# Add project root to sys.path so utils/ package is findable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Add daemon directory so chunker/embedder can be imported directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))

import yaml
from chunker import TextChunker
from embedder import EmbeddingGenerator
from utils.db_client import get_db_client

# Environment setup
from dotenv import load_dotenv
load_dotenv()

# Color output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def load_config() -> dict:
    """Load watcher configuration."""
    config_path = Path(__file__).parent.parent / "config" / "watcher.yaml"

    if not config_path.exists():
        print(f"{Colors.FAIL}Error: Config file not found at {config_path}{Colors.ENDC}")
        sys.exit(1)

    with open(config_path) as f:
        return yaml.safe_load(f)


def check_database_ready(db) -> bool:
    """Check if database tables exist."""
    try:
        # Try to query vectors.file_metadata table
        result = db.table("vectors.file_metadata").select("id").limit(1).execute()
        return True
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            return False
        # Other errors - re-raise
        raise


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def should_index_file(file_path: Path, config: dict) -> tuple[bool, str]:
    """Check if file should be indexed based on config rules.

    Returns:
        (should_index, reason)
    """
    # Check file size
    max_size_bytes = config['watcher']['max_file_size_mb'] * 1024 * 1024
    try:
        file_size = file_path.stat().st_size
        if file_size > max_size_bytes:
            return False, f"exceeds max size ({file_size / (1024*1024):.1f}MB)"
    except OSError as e:
        return False, f"cannot stat file: {e}"

    # Check extension
    include_exts = config['watcher']['include_extensions']
    if file_path.suffix not in include_exts:
        return False, f"extension {file_path.suffix} not in include list"

    # Check exclude patterns
    exclude_patterns = config['watcher']['exclude_patterns']
    path_str = str(file_path)
    for pattern in exclude_patterns:
        # Simple pattern matching (can be enhanced with fnmatch)
        if pattern.startswith("*."):
            # Extension pattern
            if path_str.endswith(pattern[1:]):
                return False, f"matches exclude pattern {pattern}"
        else:
            # Directory/file name pattern
            if pattern in path_str:
                return False, f"matches exclude pattern {pattern}"

    return True, "ok"


def scan_files(watch_paths: List[str], config: dict) -> List[Path]:
    """Scan all files in watch paths that should be indexed.

    Returns:
        List of Path objects to index
    """
    files_to_index = []

    print(f"\n{Colors.HEADER}Scanning directories...{Colors.ENDC}")

    for watch_path in watch_paths:
        path = Path(watch_path)

        if not path.exists():
            print(f"{Colors.WARNING}Warning: Path does not exist: {watch_path}{Colors.ENDC}")
            continue

        print(f"  Scanning: {watch_path}")

        # Walk directory tree
        for root, dirs, files in os.walk(path):
            root_path = Path(root)

            # Filter out excluded directories in-place
            exclude_patterns = config['watcher']['exclude_patterns']
            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclude_patterns if not pattern.startswith("*"))]

            for file in files:
                file_path = root_path / file

                should_index, reason = should_index_file(file_path, config)
                if should_index:
                    files_to_index.append(file_path)

    return files_to_index


def get_indexed_files(db) -> Dict[str, tuple]:
    """Get currently indexed files from database.

    Returns:
        Dict mapping file_path -> (content_hash, updated_at)
    """
    try:
        result = db.table("vectors.file_metadata").select("file_path,content_hash,updated_at").execute()

        indexed = {}
        for row in result.data:
            indexed[row['file_path']] = (row['content_hash'], row['updated_at'])

        return indexed
    except Exception as e:
        print(f"{Colors.FAIL}Error querying indexed files: {e}{Colors.ENDC}")
        return {}


def classify_files(files: List[Path], indexed_files: Dict[str, tuple]) -> Dict[str, List[Path]]:
    """Classify files into new, modified, unchanged.

    Returns:
        Dict with keys: 'new', 'modified', 'unchanged'
    """
    classification = {
        'new': [],
        'modified': [],
        'unchanged': []
    }

    for file_path in files:
        path_str = str(file_path)

        if path_str not in indexed_files:
            classification['new'].append(file_path)
        else:
            # Check if hash changed
            current_hash = compute_file_hash(file_path)
            indexed_hash, _ = indexed_files[path_str]

            if current_hash != indexed_hash:
                classification['modified'].append(file_path)
            else:
                classification['unchanged'].append(file_path)

    return classification


def index_file(file_path: Path, chunker: TextChunker, embedder: EmbeddingGenerator,
               db, dry_run: bool = False) -> tuple[bool, str]:
    """Index a single file.

    Returns:
        (success, message)
    """
    try:
        # Read file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            return False, "not UTF-8 text"

        # Compute content hash (matches worker.py convention)
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        file_size = file_path.stat().st_size
        line_count = content.count('\n') + 1

        # Chunk text
        chunks = chunker.chunk_text(content)

        if not chunks:
            return False, "no chunks generated (empty file?)"

        # Compute total token count across all chunks
        token_count = sum(chunk.token_count for chunk in chunks)

        if dry_run:
            return True, f"would index {len(chunks)} chunks"

        # Insert/update vectors.file_metadata using schema-aligned column names
        now = datetime.utcnow().isoformat()
        file_metadata = {
            "file_path": str(file_path),
            "content_hash": content_hash,
            "file_size": file_size,
            "line_count": line_count,
            "token_count": token_count,
            "chunk_count": len(chunks),
            "index_status": "indexed",
            "indexed_at": now,
            "modified_at": now
        }

        # Upsert file metadata
        db.table("vectors.file_metadata").upsert(
            file_metadata,
            on_conflict="file_path"
        ).execute()

        # Get file_id
        result = db.table("vectors.file_metadata").select("id").eq(
            "file_path", str(file_path)
        ).execute()
        file_id = result.data[0]['id']

        # Delete old chunks for this file (cascade will delete embeddings)
        db.table("vectors.file_chunks").delete().eq("file_id", file_id).execute()

        # Generate embeddings for chunks
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedder.embed_batch(chunk_texts)

        # Insert chunks and embeddings
        for chunk, embedding in zip(chunks, embeddings):
            chunk_data = {
                "file_id": file_id,
                "chunk_index": chunk.index,
                "content": chunk.text,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "char_offset": chunk.char_offset,
                "token_count": chunk.token_count
            }

            # Insert chunk
            chunk_result = db.table("vectors.file_chunks").insert(chunk_data).execute()
            chunk_id = chunk_result.data[0]['id']

            # Insert embedding
            embedding_data = {
                "chunk_id": chunk_id,
                "embedding": embedding
            }
            db.table("vectors.file_embeddings").insert(embedding_data).execute()

        return True, f"indexed {len(chunks)} chunks"

    except Exception as e:
        return False, f"error: {str(e)[:100]}"


def main():
    parser = argparse.ArgumentParser(description="Bulk index files for vector search")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be indexed without actually indexing"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform indexing"
    )
    parser.add_argument(
        "--path",
        type=str,
        help="Index specific path instead of all configured paths"
    )
    parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        default=True,
        help="Skip files that haven't changed (default: True)"
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print(f"{Colors.FAIL}Error: Must specify either --dry-run or --execute{Colors.ENDC}")
        parser.print_help()
        sys.exit(1)

    # Load configuration
    config = load_config()

    # Setup database client
    db = get_db_client()

    # Check if database is ready
    print(f"\n{Colors.HEADER}Checking database...{Colors.ENDC}")
    if not check_database_ready(db):
        print(f"{Colors.FAIL}ERROR: Database tables do not exist!{Colors.ENDC}")
        print(f"\n{Colors.WARNING}Please run the migration first:{Colors.ENDC}")
        print(f"  1. Connect to PostgreSQL at {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5433')}")
        print(f"  2. Execute: /srv/latvian_mcp/migrations/020_vector_search_indexer.sql")
        sys.exit(1)

    print(f"{Colors.OKGREEN}Database tables exist{Colors.ENDC}")

    # Determine paths to scan
    if args.path:
        watch_paths = [args.path]
        print(f"\n{Colors.HEADER}Indexing specific path: {args.path}{Colors.ENDC}")
    else:
        watch_paths = config['watcher']['watch_paths']
        print(f"\n{Colors.HEADER}Indexing configured watch paths{Colors.ENDC}")

    # Scan files
    files_to_scan = scan_files(watch_paths, config)
    print(f"\n{Colors.OKGREEN}Found {len(files_to_scan)} files matching criteria{Colors.ENDC}")

    if not files_to_scan:
        print(f"{Colors.WARNING}No files to index{Colors.ENDC}")
        return

    # Get currently indexed files
    if not args.dry_run:
        print(f"\n{Colors.HEADER}Checking existing index...{Colors.ENDC}")
        indexed_files = get_indexed_files(db)
        print(f"  Currently indexed: {len(indexed_files)} files")

        # Classify files
        classification = classify_files(files_to_scan, indexed_files)

        print(f"\n{Colors.HEADER}Classification:{Colors.ENDC}")
        print(f"  {Colors.OKGREEN}New files:{Colors.ENDC} {len(classification['new'])}")
        print(f"  {Colors.WARNING}Modified files:{Colors.ENDC} {len(classification['modified'])}")
        print(f"  {Colors.OKBLUE}Unchanged files:{Colors.ENDC} {len(classification['unchanged'])}")

        # Determine which files to index
        if args.skip_unchanged:
            files_to_index = classification['new'] + classification['modified']
            print(f"\n{Colors.OKGREEN}Will index {len(files_to_index)} files (skipping {len(classification['unchanged'])} unchanged){Colors.ENDC}")
        else:
            files_to_index = files_to_scan
            print(f"\n{Colors.OKGREEN}Will index all {len(files_to_index)} files{Colors.ENDC}")
    else:
        files_to_index = files_to_scan

    if args.dry_run:
        print(f"\n{Colors.HEADER}DRY RUN - Preview of files to index:{Colors.ENDC}")
        for i, file_path in enumerate(files_to_index[:20], 1):
            print(f"  {i}. {file_path}")

        if len(files_to_index) > 20:
            print(f"  ... and {len(files_to_index) - 20} more files")

        print(f"\n{Colors.OKCYAN}To actually index these files, run with --execute{Colors.ENDC}")
        return

    # Initialize chunker and embedder
    print(f"\n{Colors.HEADER}Initializing chunker and embedder...{Colors.ENDC}")
    chunker = TextChunker(max_tokens=500, overlap_tokens=50)
    embedder = EmbeddingGenerator(device='cpu')  # Force CPU mode to avoid CUDA compatibility issues

    # Index files
    print(f"\n{Colors.HEADER}Indexing files...{Colors.ENDC}")

    start_time = time.time()
    success_count = 0
    error_count = 0

    for i, file_path in enumerate(files_to_index, 1):
        # Progress
        elapsed = time.time() - start_time
        if i > 1:
            avg_time = elapsed / (i - 1)
            remaining = avg_time * (len(files_to_index) - i)
            eta = f"ETA: {remaining/60:.1f}m"
        else:
            eta = "calculating..."

        print(f"\n[{i}/{len(files_to_index)}] {Colors.BOLD}{file_path.name}{Colors.ENDC} ({eta})")
        print(f"  Path: {file_path}")

        success, message = index_file(file_path, chunker, embedder, db, dry_run=False)

        if success:
            print(f"  {Colors.OKGREEN}{message}{Colors.ENDC}")
            success_count += 1
        else:
            print(f"  {Colors.FAIL}{message}{Colors.ENDC}")
            error_count += 1

    # Summary
    total_time = time.time() - start_time

    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}BULK INDEX COMPLETE{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\n{Colors.OKGREEN}Success:{Colors.ENDC} {success_count} files")
    print(f"{Colors.FAIL}Errors:{Colors.ENDC} {error_count} files")
    print(f"{Colors.OKCYAN}Total time:{Colors.ENDC} {total_time/60:.1f} minutes")
    print(f"{Colors.OKCYAN}Average:{Colors.ENDC} {total_time/len(files_to_index):.1f} seconds per file")

    print(f"\n{Colors.OKGREEN}Next steps:{Colors.ENDC}")
    print(f"  1. Run verification: python scripts/verify_index.py")
    print(f"  2. Optimize index: python scripts/optimize_index.py")


if __name__ == "__main__":
    main()
