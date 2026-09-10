DROP INDEX IF EXISTS ix_raw_documents_content_hash;
ALTER TABLE raw_documents DROP CONSTRAINT IF EXISTS raw_documents_content_hash_key;
CREATE INDEX IF NOT EXISTS ix_raw_documents_content_hash ON raw_documents(content_hash);
