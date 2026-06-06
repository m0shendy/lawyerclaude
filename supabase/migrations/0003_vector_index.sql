-- 0003_vector_index.sql
-- HNSW (cosine) indexes for RAG retrieval (R2). No training step, good
-- recall/latency at tens-of-thousands of chunks per firm.

create index idx_document_chunks_embedding
    on document_chunks
    using hnsw (embedding vector_cosine_ops);

create index idx_reference_chunks_embedding
    on reference_chunks
    using hnsw (embedding vector_cosine_ops);
