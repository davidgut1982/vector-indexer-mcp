#!/usr/bin/env python3
"""
Verify Index Script - Vector Indexer MCP

Validates the integrity of the vector index by checking:
- File count matches filesystem
- All chunks have embeddings
- No orphaned records
- Index health statistics

Usage:
    python scripts/verify_index.py
    python scripts/verify_index.py --path /specific/path
    python scripts/verify_index.py --fix-orphans  # Remove orphaned records
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Set

from supabase import create_client, Client
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


def check_database_ready(supabase: Client) -> bool:
    """Check if database tables exist."""
    try:
        supabase.table("file_metadata").select("id").limit(1).execute()
        return True
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            return False
        raise


def get_index_health(supabase: Client) -> Dict:
    """Get index health statistics from database."""
    try:
        # File metadata count
        files_result = supabase.table("file_metadata").select("id", count="exact").execute()
        file_count = files_result.count

        # Chunks count
        chunks_result = supabase.table("file_chunks").select("id", count="exact").execute()
        chunk_count = chunks_result.count

        # Embeddings count
        embeddings_result = supabase.table("file_embeddings").select("id", count="exact").execute()
        embedding_count = embeddings_result.count

        # Total size of indexed files
        size_result = supabase.rpc("get_total_indexed_size").execute()
        total_size = size_result.data if size_result.data else 0

        return {
            "file_count": file_count,
            "chunk_count": chunk_count,
            "embedding_count": embedding_count,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024) if total_size else 0
        }
    except Exception as e:
        return {
            "error": str(e)
        }


def check_filesystem_sync(supabase: Client, watch_path: str = None) -> Dict:
    """Check if indexed files match filesystem.

    Returns:
        Dict with 'indexed_only', 'filesystem_only', 'match' keys
    """
    # Get indexed files
    result = supabase.table("file_metadata").select("file_path").execute()
    indexed_files = set(row['file_path'] for row in result.data)

    # Get filesystem files (simplified - doesn't check patterns)
    filesystem_files = set()

    if watch_path:
        paths_to_check = [Path(watch_path)]
    else:
        # Use default watch paths
        paths_to_check = [
            Path("/srv/latvian_mcp"),
            Path("/srv/latvian_xtts"),
            Path("/srv/latvian_learning"),
            Path("/srv/claude-mpm")
        ]

    for path in paths_to_check:
        if not path.exists():
            continue

        for root, dirs, files in os.walk(path):
            # Skip common excluded directories
            exclude_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'dist', 'build'}
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                # Check if it's a text file (has text extension)
                if file_path.suffix in {'.py', '.md', '.txt', '.json', '.yaml', '.yml', '.sql', '.sh', '.toml', '.ini', '.cfg', '.conf'}:
                    filesystem_files.add(str(file_path))

    # Compare
    indexed_only = indexed_files - filesystem_files
    filesystem_only = filesystem_files - indexed_files
    match = indexed_files & filesystem_files

    return {
        "indexed_only": list(indexed_only),
        "filesystem_only": list(filesystem_only),
        "match": list(match),
        "indexed_count": len(indexed_files),
        "filesystem_count": len(filesystem_files),
        "match_count": len(match)
    }


def check_chunks_have_embeddings(supabase: Client) -> Dict:
    """Check if all chunks have corresponding embeddings."""
    # Get chunk IDs
    chunks_result = supabase.table("file_chunks").select("id").execute()
    chunk_ids = set(row['id'] for row in chunks_result.data)

    # Get embedding chunk IDs
    embeddings_result = supabase.table("file_embeddings").select("chunk_id").execute()
    embedding_chunk_ids = set(row['chunk_id'] for row in embeddings_result.data)

    # Find chunks without embeddings
    missing_embeddings = chunk_ids - embedding_chunk_ids

    return {
        "total_chunks": len(chunk_ids),
        "chunks_with_embeddings": len(embedding_chunk_ids),
        "chunks_without_embeddings": len(missing_embeddings),
        "missing_chunk_ids": list(missing_embeddings)
    }


def check_orphaned_records(supabase: Client) -> Dict:
    """Check for orphaned chunks and embeddings."""
    # Get file IDs
    files_result = supabase.table("file_metadata").select("id").execute()
    file_ids = set(row['id'] for row in files_result.data)

    # Get chunks with their file_ids
    chunks_result = supabase.table("file_chunks").select("id,file_id").execute()
    chunk_file_ids = {row['id']: row['file_id'] for row in chunks_result.data}

    # Find orphaned chunks (file_id doesn't exist)
    orphaned_chunks = [
        chunk_id for chunk_id, file_id in chunk_file_ids.items()
        if file_id not in file_ids
    ]

    # Get chunk IDs
    chunk_ids = set(chunk_file_ids.keys())

    # Get embeddings with chunk_ids
    embeddings_result = supabase.table("file_embeddings").select("id,chunk_id").execute()
    embedding_chunk_ids = {row['id']: row['chunk_id'] for row in embeddings_result.data}

    # Find orphaned embeddings (chunk_id doesn't exist)
    orphaned_embeddings = [
        emb_id for emb_id, chunk_id in embedding_chunk_ids.items()
        if chunk_id not in chunk_ids
    ]

    return {
        "orphaned_chunks": len(orphaned_chunks),
        "orphaned_chunk_ids": orphaned_chunks,
        "orphaned_embeddings": len(orphaned_embeddings),
        "orphaned_embedding_ids": orphaned_embeddings
    }


def fix_orphaned_records(supabase: Client, orphaned: Dict) -> Dict:
    """Remove orphaned records from database."""
    deleted = {
        "chunks": 0,
        "embeddings": 0
    }

    # Delete orphaned embeddings
    for emb_id in orphaned['orphaned_embedding_ids']:
        try:
            supabase.table("file_embeddings").delete().eq("id", emb_id).execute()
            deleted['embeddings'] += 1
        except Exception as e:
            print(f"{Colors.WARNING}Warning: Failed to delete embedding {emb_id}: {e}{Colors.ENDC}")

    # Delete orphaned chunks
    for chunk_id in orphaned['orphaned_chunk_ids']:
        try:
            supabase.table("file_chunks").delete().eq("id", chunk_id).execute()
            deleted['chunks'] += 1
        except Exception as e:
            print(f"{Colors.WARNING}Warning: Failed to delete chunk {chunk_id}: {e}{Colors.ENDC}")

    return deleted


def main():
    parser = argparse.ArgumentParser(description="Verify vector index integrity")
    parser.add_argument(
        "--path",
        type=str,
        help="Verify specific path instead of all configured paths"
    )
    parser.add_argument(
        "--fix-orphans",
        action="store_true",
        help="Remove orphaned records"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed lists of mismatches"
    )

    args = parser.parse_args()

    # Setup Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print(f"{Colors.FAIL}Error: SUPABASE_URL and SUPABASE_SERVICE_KEY/SUPABASE_KEY must be set{Colors.ENDC}")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    # Check database
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}VECTOR INDEX VERIFICATION{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")

    print(f"\n{Colors.HEADER}Checking database...{Colors.ENDC}")
    if not check_database_ready(supabase):
        print(f"{Colors.FAIL}ERROR: Database tables do not exist!{Colors.ENDC}")
        print(f"\n{Colors.WARNING}Please run the migration first.{Colors.ENDC}")
        sys.exit(1)

    print(f"{Colors.OKGREEN}✓ Database tables exist{Colors.ENDC}")

    # Get index health
    print(f"\n{Colors.HEADER}Index Health Statistics{Colors.ENDC}")
    health = get_index_health(supabase)

    if "error" in health:
        print(f"{Colors.FAIL}Error getting health stats: {health['error']}{Colors.ENDC}")
    else:
        print(f"  Files indexed: {health['file_count']}")
        print(f"  Text chunks: {health['chunk_count']}")
        print(f"  Embeddings: {health['embedding_count']}")
        print(f"  Total size: {health['total_size_mb']:.2f} MB")

        # Check if counts match
        if health['chunk_count'] == health['embedding_count']:
            print(f"  {Colors.OKGREEN}✓ Chunk count matches embedding count{Colors.ENDC}")
        else:
            print(f"  {Colors.FAIL}✗ Chunk count ({health['chunk_count']}) != embedding count ({health['embedding_count']}){Colors.ENDC}")

    # Check filesystem sync
    print(f"\n{Colors.HEADER}Filesystem Synchronization{Colors.ENDC}")
    sync = check_filesystem_sync(supabase, args.path)

    print(f"  Files in index: {sync['indexed_count']}")
    print(f"  Files in filesystem: {sync['filesystem_count']}")
    print(f"  Matching: {sync['match_count']}")

    if sync['indexed_only']:
        print(f"  {Colors.WARNING}⚠ Files in index but not filesystem: {len(sync['indexed_only'])}{Colors.ENDC}")
        if args.detailed and len(sync['indexed_only']) <= 50:
            for f in sync['indexed_only'][:20]:
                print(f"    - {f}")
            if len(sync['indexed_only']) > 20:
                print(f"    ... and {len(sync['indexed_only']) - 20} more")

    if sync['filesystem_only']:
        print(f"  {Colors.WARNING}⚠ Files in filesystem but not indexed: {len(sync['filesystem_only'])}{Colors.ENDC}")
        if args.detailed and len(sync['filesystem_only']) <= 50:
            for f in sync['filesystem_only'][:20]:
                print(f"    - {f}")
            if len(sync['filesystem_only']) > 20:
                print(f"    ... and {len(sync['filesystem_only']) - 20} more")

    # Check chunks have embeddings
    print(f"\n{Colors.HEADER}Chunks & Embeddings Integrity{Colors.ENDC}")
    chunks_check = check_chunks_have_embeddings(supabase)

    print(f"  Total chunks: {chunks_check['total_chunks']}")
    print(f"  Chunks with embeddings: {chunks_check['chunks_with_embeddings']}")

    if chunks_check['chunks_without_embeddings'] == 0:
        print(f"  {Colors.OKGREEN}✓ All chunks have embeddings{Colors.ENDC}")
    else:
        print(f"  {Colors.FAIL}✗ Chunks without embeddings: {chunks_check['chunks_without_embeddings']}{Colors.ENDC}")
        if args.detailed and chunks_check['missing_chunk_ids']:
            print(f"    Missing chunk IDs: {chunks_check['missing_chunk_ids'][:10]}")

    # Check orphaned records
    print(f"\n{Colors.HEADER}Orphaned Records Check{Colors.ENDC}")
    orphaned = check_orphaned_records(supabase)

    print(f"  Orphaned chunks: {orphaned['orphaned_chunks']}")
    print(f"  Orphaned embeddings: {orphaned['orphaned_embeddings']}")

    if orphaned['orphaned_chunks'] == 0 and orphaned['orphaned_embeddings'] == 0:
        print(f"  {Colors.OKGREEN}✓ No orphaned records{Colors.ENDC}")
    else:
        print(f"  {Colors.WARNING}⚠ Found orphaned records{Colors.ENDC}")

        if args.fix_orphans:
            print(f"\n{Colors.HEADER}Fixing orphaned records...{Colors.ENDC}")
            deleted = fix_orphaned_records(supabase, orphaned)
            print(f"  {Colors.OKGREEN}✓ Deleted {deleted['chunks']} orphaned chunks{Colors.ENDC}")
            print(f"  {Colors.OKGREEN}✓ Deleted {deleted['embeddings']} orphaned embeddings{Colors.ENDC}")

    # Overall status
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")

    issues = []
    if health.get('chunk_count', 0) != health.get('embedding_count', 0):
        issues.append("Chunk/embedding count mismatch")
    if chunks_check['chunks_without_embeddings'] > 0:
        issues.append("Chunks without embeddings")
    if orphaned['orphaned_chunks'] > 0 or orphaned['orphaned_embeddings'] > 0:
        issues.append("Orphaned records")

    if not issues:
        print(f"{Colors.OKGREEN}{Colors.BOLD}✓ INDEX VERIFICATION PASSED{Colors.ENDC}")
        print(f"{Colors.OKGREEN}All checks passed - index is healthy{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}{Colors.BOLD}⚠ INDEX VERIFICATION FOUND ISSUES{Colors.ENDC}")
        print(f"{Colors.WARNING}Issues found:{Colors.ENDC}")
        for issue in issues:
            print(f"  - {issue}")

        print(f"\n{Colors.OKCYAN}Recommendations:{Colors.ENDC}")
        if orphaned['orphaned_chunks'] > 0 or orphaned['orphaned_embeddings'] > 0:
            print(f"  - Run with --fix-orphans to remove orphaned records")
        if sync['filesystem_only']:
            print(f"  - Run bulk_index.py to index missing files")


if __name__ == "__main__":
    main()
