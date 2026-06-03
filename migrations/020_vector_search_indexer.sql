-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- File metadata table
CREATE TABLE IF NOT EXISTS file_metadata (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT,
    file_size INTEGER,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- File chunks table
CREATE TABLE IF NOT EXISTS file_chunks (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_start_line INTEGER,
    chunk_end_line INTEGER,
    token_count INTEGER,
    fts_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED
);

-- File embeddings table (384-dim for paraphrase-multilingual-MiniLM-L12-v2)
CREATE TABLE IF NOT EXISTS file_embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER REFERENCES file_chunks(id) ON DELETE CASCADE,
    embedding vector(384)
);

-- Index queue table
CREATE TABLE IF NOT EXISTS index_queue (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- Index stats table
CREATE TABLE IF NOT EXISTS index_stats (
    id SERIAL PRIMARY KEY,
    stat_time TIMESTAMPTZ DEFAULT NOW(),
    total_files INTEGER,
    total_chunks INTEGER,
    total_embeddings INTEGER,
    queue_pending INTEGER
);

-- Indexes
CREATE INDEX IF NOT EXISTS file_chunks_fts_idx ON file_chunks USING GIN(fts_vector);
CREATE INDEX IF NOT EXISTS file_embeddings_hnsw_idx ON file_embeddings USING hnsw(embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS file_metadata_path_idx ON file_metadata(file_path);
CREATE INDEX IF NOT EXISTS index_queue_status_idx ON index_queue(status);

-- Hybrid search function
CREATE OR REPLACE FUNCTION search_hybrid(
    query_text TEXT,
    query_embedding vector(384),
    result_limit INTEGER DEFAULT 20,
    alpha FLOAT DEFAULT 0.5
)
RETURNS TABLE(
    chunk_id INTEGER,
    file_path TEXT,
    chunk_text TEXT,
    chunk_start_line INTEGER,
    chunk_end_line INTEGER,
    fts_rank FLOAT,
    vector_similarity FLOAT,
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH fts_results AS (
        SELECT
            fc.id,
            fm.file_path,
            fc.chunk_text,
            fc.chunk_start_line,
            fc.chunk_end_line,
            ts_rank(fc.fts_vector, plainto_tsquery('english', query_text))::FLOAT as fts_rank,
            0.0::FLOAT as vector_sim
        FROM file_chunks fc
        JOIN file_metadata fm ON fc.file_id = fm.id
        WHERE fc.fts_vector @@ plainto_tsquery('english', query_text)
    ),
    vector_results AS (
        SELECT
            fc.id,
            fm.file_path,
            fc.chunk_text,
            fc.chunk_start_line,
            fc.chunk_end_line,
            0.0::FLOAT as fts_rank,
            (1 - (fe.embedding <=> query_embedding))::FLOAT as vector_sim
        FROM file_embeddings fe
        JOIN file_chunks fc ON fe.chunk_id = fc.id
        JOIN file_metadata fm ON fc.file_id = fm.id
    ),
    combined AS (
        SELECT
            COALESCE(f.id, v.id) as id,
            COALESCE(f.file_path, v.file_path) as file_path,
            COALESCE(f.chunk_text, v.chunk_text) as chunk_text,
            COALESCE(f.chunk_start_line, v.chunk_start_line) as chunk_start_line,
            COALESCE(f.chunk_end_line, v.chunk_end_line) as chunk_end_line,
            COALESCE(f.fts_rank, 0.0) as fts_rank,
            COALESCE(v.vector_sim, 0.0) as vector_sim
        FROM fts_results f
        FULL OUTER JOIN vector_results v ON f.id = v.id
    )
    SELECT
        c.id,
        c.file_path,
        c.chunk_text,
        c.chunk_start_line,
        c.chunk_end_line,
        c.fts_rank,
        c.vector_sim,
        (alpha * c.vector_sim + (1-alpha) * c.fts_rank)::FLOAT as combined_score
    FROM combined c
    ORDER BY combined_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Index health function
CREATE OR REPLACE FUNCTION get_index_health()
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_files', (SELECT COUNT(*) FROM file_metadata),
        'total_chunks', (SELECT COUNT(*) FROM file_chunks),
        'total_embeddings', (SELECT COUNT(*) FROM file_embeddings),
        'pending_queue', (SELECT COUNT(*) FROM index_queue WHERE status = 'pending'),
        'last_indexed', (SELECT MAX(indexed_at) FROM file_metadata)
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql;
