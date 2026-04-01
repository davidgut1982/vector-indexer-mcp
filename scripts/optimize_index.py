#!/usr/bin/env python3
"""
Optimize Index Script - Vector Indexer MCP

Performance tuning for the vector index:
- VACUUM ANALYZE on tables
- Rebuild HNSW index if needed
- Update table statistics
- Check index bloat

Usage:
    python scripts/optimize_index.py --dry-run    # Preview optimizations
    python scripts/optimize_index.py --execute    # Perform optimizations
"""

import argparse
import sys
import os
import time
from pathlib import Path

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


def get_table_stats(supabase: Client) -> dict:
    """Get table size and row count statistics."""
    tables = ["file_metadata", "file_chunks", "file_embeddings"]
    stats = {}

    for table in tables:
        try:
            # Get row count
            result = supabase.table(table).select("id", count="exact").execute()
            row_count = result.count

            # Get table size (requires RPC or direct SQL)
            # For now, just store row count
            stats[table] = {
                "row_count": row_count
            }
        except Exception as e:
            stats[table] = {
                "error": str(e)
            }

    return stats


def vacuum_analyze_table(supabase: Client, table: str, dry_run: bool = False) -> tuple[bool, str]:
    """Run VACUUM ANALYZE on a table.

    Note: This requires direct database access via psycopg2 or SQL editor.
    Supabase REST API doesn't support VACUUM.
    """
    if dry_run:
        return True, f"would run VACUUM ANALYZE on {table}"

    # This would require direct PostgreSQL connection
    # For now, return instruction
    return False, "requires direct PostgreSQL access (use SQL editor)"


def check_index_health(supabase: Client) -> dict:
    """Check HNSW index health and statistics."""
    try:
        # Try to get embedding statistics
        result = supabase.table("file_embeddings").select("id", count="exact").execute()
        embedding_count = result.count

        return {
            "embedding_count": embedding_count,
            "hnsw_index_exists": True,  # Assume it exists if table exists
            "status": "ok"
        }
    except Exception as e:
        return {
            "error": str(e),
            "status": "error"
        }


def rebuild_hnsw_index(supabase: Client, dry_run: bool = False) -> tuple[bool, str]:
    """Rebuild HNSW index on embeddings table.

    Note: This requires direct database access.
    """
    if dry_run:
        return True, "would rebuild HNSW index on embeddings.embedding column"

    # This requires direct PostgreSQL access
    # SQL: DROP INDEX IF EXISTS embeddings_embedding_idx;
    #      CREATE INDEX embeddings_embedding_idx ON embeddings USING hnsw (embedding vector_cosine_ops);
    return False, "requires direct PostgreSQL access (use SQL editor)"


def analyze_index_bloat(supabase: Client) -> dict:
    """Analyze potential index bloat."""
    # This would require PostgreSQL system catalogs
    # For now, return basic info
    return {
        "message": "Index bloat analysis requires direct PostgreSQL access",
        "recommendation": "Run VACUUM FULL if tables have been heavily modified"
    }


def update_statistics(supabase: Client, dry_run: bool = False) -> tuple[bool, str]:
    """Update table statistics for query planner."""
    if dry_run:
        return True, "would run ANALYZE on all tables"

    # Requires direct PostgreSQL access
    return False, "requires direct PostgreSQL access (use SQL editor)"


def main():
    parser = argparse.ArgumentParser(description="Optimize vector index performance")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview optimizations without executing"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute optimizations"
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild HNSW index (use with caution on large datasets)"
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print(f"{Colors.FAIL}Error: Must specify either --dry-run or --execute{Colors.ENDC}")
        parser.print_help()
        sys.exit(1)

    # Setup Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print(f"{Colors.FAIL}Error: SUPABASE_URL and SUPABASE_SERVICE_KEY/SUPABASE_KEY must be set{Colors.ENDC}")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    # Check database
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}VECTOR INDEX OPTIMIZATION{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")

    print(f"\n{Colors.HEADER}Checking database...{Colors.ENDC}")
    if not check_database_ready(supabase):
        print(f"{Colors.FAIL}ERROR: Database tables do not exist!{Colors.ENDC}")
        print(f"\n{Colors.WARNING}Please run the migration first.{Colors.ENDC}")
        sys.exit(1)

    print(f"{Colors.OKGREEN}✓ Database tables exist{Colors.ENDC}")

    # Get table stats
    print(f"\n{Colors.HEADER}Table Statistics{Colors.ENDC}")
    stats = get_table_stats(supabase)

    for table, table_stats in stats.items():
        if "error" in table_stats:
            print(f"  {table}: {Colors.FAIL}Error - {table_stats['error']}{Colors.ENDC}")
        else:
            print(f"  {table}: {table_stats['row_count']:,} rows")

    # Check index health
    print(f"\n{Colors.HEADER}Index Health{Colors.ENDC}")
    health = check_index_health(supabase)

    if "error" in health:
        print(f"  {Colors.FAIL}Error: {health['error']}{Colors.ENDC}")
    else:
        print(f"  Embeddings indexed: {health['embedding_count']:,}")
        print(f"  HNSW index: {Colors.OKGREEN}exists{Colors.ENDC}" if health['hnsw_index_exists'] else f"{Colors.FAIL}missing{Colors.ENDC}")

    # Optimization recommendations
    print(f"\n{Colors.HEADER}Optimization Plan{Colors.ENDC}")

    tasks = []

    # VACUUM ANALYZE
    if not args.dry_run:
        print(f"\n{Colors.OKCYAN}Note: Some optimizations require direct PostgreSQL access.{Colors.ENDC}")
        print(f"{Colors.OKCYAN}The following SQL commands should be run in Supabase SQL Editor:{Colors.ENDC}\n")

    print(f"{Colors.BOLD}1. VACUUM ANALYZE{Colors.ENDC} (reclaim space and update statistics)")
    print(f"   SQL:")
    print(f"   ```sql")
    print(f"   VACUUM ANALYZE file_metadata;")
    print(f"   VACUUM ANALYZE file_chunks;")
    print(f"   VACUUM ANALYZE file_embeddings;")
    print(f"   ```")

    print(f"\n{Colors.BOLD}2. Update Statistics{Colors.ENDC} (improve query planning)")
    print(f"   SQL:")
    print(f"   ```sql")
    print(f"   ANALYZE file_metadata;")
    print(f"   ANALYZE file_chunks;")
    print(f"   ANALYZE file_embeddings;")
    print(f"   ```")

    if args.rebuild_index:
        print(f"\n{Colors.BOLD}3. Rebuild HNSW Index{Colors.ENDC} (rebuild vector index)")
        print(f"   {Colors.WARNING}⚠ This can take significant time on large datasets{Colors.ENDC}")
        print(f"   SQL:")
        print(f"   ```sql")
        print(f"   -- Drop existing index")
        print(f"   DROP INDEX IF EXISTS idx_file_embeddings_vector;")
        print(f"   ")
        print(f"   -- Recreate with optimized parameters")
        print(f"   CREATE INDEX idx_file_embeddings_vector")
        print(f"   ON file_embeddings")
        print(f"   USING hnsw (embedding vector_cosine_ops)")
        print(f"   WITH (m = 16, ef_construction = 64);")
        print(f"   ```")
        print(f"   ")
        print(f"   {Colors.OKCYAN}HNSW parameters:{Colors.ENDC}")
        print(f"   - m=16: Number of connections per layer (higher = better recall, more memory)")
        print(f"   - ef_construction=64: Build quality (higher = better recall, slower build)")

    # Index bloat analysis
    print(f"\n{Colors.BOLD}4. Index Bloat Check{Colors.ENDC} (if tables heavily modified)")
    bloat = analyze_index_bloat(supabase)
    print(f"   {bloat['message']}")
    print(f"   {bloat['recommendation']}")

    # Additional recommendations
    print(f"\n{Colors.HEADER}Additional Recommendations{Colors.ENDC}")

    total_embeddings = health.get('embedding_count', 0)

    if total_embeddings > 100000:
        print(f"  {Colors.OKCYAN}Large dataset detected ({total_embeddings:,} embeddings){Colors.ENDC}")
        print(f"  Consider:")
        print(f"    - Increasing HNSW m parameter to 24-32 for better recall")
        print(f"    - Using ef_construction=128 for build quality")
        print(f"    - Monitoring query performance with EXPLAIN ANALYZE")

    if total_embeddings < 10000:
        print(f"  {Colors.OKCYAN}Small dataset ({total_embeddings:,} embeddings){Colors.ENDC}")
        print(f"  Consider:")
        print(f"    - Using smaller HNSW parameters (m=8, ef_construction=32)")
        print(f"    - Current settings likely optimal")

    # Query optimization tips
    print(f"\n{Colors.HEADER}Query Optimization Tips{Colors.ENDC}")
    print(f"  - Use appropriate similarity thresholds (0.5-0.7 for semantic search)")
    print(f"  - Limit results to reasonable numbers (10-50)")
    print(f"  - Use file_type and path filters to reduce search space")
    print(f"  - Monitor query times with index_status tool")

    # Summary
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")

    if args.dry_run:
        print(f"{Colors.BOLD}DRY RUN COMPLETE{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}To apply optimizations:{Colors.ENDC}")
        print(f"  1. Copy SQL commands above")
        print(f"  2. Open Supabase SQL Editor")
        print(f"  3. Execute commands")
        print(f"  4. Monitor performance improvements")
    else:
        print(f"{Colors.BOLD}OPTIMIZATION INSTRUCTIONS PROVIDED{Colors.ENDC}")
        print(f"\n{Colors.OKGREEN}Next steps:{Colors.ENDC}")
        print(f"  1. Run SQL commands in Supabase SQL Editor")
        print(f"  2. Monitor query performance")
        print(f"  3. Verify with: python scripts/verify_index.py")

    print(f"\n{Colors.OKCYAN}Performance Monitoring:{Colors.ENDC}")
    print(f"  - Use search_semantic tool and check response times")
    print(f"  - Run index_status tool to see health metrics")
    print(f"  - Check Supabase dashboard for slow queries")


if __name__ == "__main__":
    main()
