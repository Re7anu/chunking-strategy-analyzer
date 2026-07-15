-- Enable the pgvector extension to allow vector data types and similarity operators
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the documentation chunks table
CREATE TABLE IF NOT EXISTS analyzer_chunks (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    -- all-MiniLM-L6-v2 generates 384-dimensional vectors
    embedding VECTOR(384) NOT NULL,
    -- TSVECTOR column generated automatically from content for full-text search
    fts_tokens TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create an HNSW index on the vector embedding column using cosine distance similarity (<=>)
-- Note: m=16, ef_construction=64 are standard values, adjusting for vector size
CREATE INDEX IF NOT EXISTS analyzer_chunks_embedding_hnsw_idx 
ON analyzer_chunks USING hnsw (embedding vector_cosine_ops);

-- Create a GIN index on the TSVECTOR column to optimize full-text keyword searches
CREATE INDEX IF NOT EXISTS analyzer_chunks_fts_idx 
ON analyzer_chunks USING gin (fts_tokens);
