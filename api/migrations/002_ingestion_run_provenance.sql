-- Preserve whether evidence came from historical playback or an operator-run
-- TinyFish source check, along with sanitized retrieval metadata.

BEGIN;

ALTER TABLE public.ingestion_runs
    ADD COLUMN IF NOT EXISTS provider_run_url VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE public.ingestion_runs
    ADD COLUMN IF NOT EXISTS source_kind VARCHAR(32) NOT NULL DEFAULT 'unknown';
ALTER TABLE public.ingestion_runs
    ADD COLUMN IF NOT EXISTS retrieval_metadata JSON NOT NULL DEFAULT '{}'::json;

-- Existing columns must match the API contract; IF NOT EXISTS alone can leave
-- an older nullable or incorrectly typed prototype silently incompatible.
DO $$
DECLARE required RECORD;
BEGIN
    FOR required IN SELECT * FROM (VALUES
        ('provider_run_url', 'character varying(500)'),
        ('source_kind', 'character varying(32)'),
        ('retrieval_metadata', 'json')
    ) AS columns(column_name, type_name)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_attribute a
            WHERE a.attrelid = 'public.ingestion_runs'::regclass
              AND a.attname = required.column_name AND NOT a.attisdropped
              AND a.attnotnull AND format_type(a.atttypid, a.atttypmod) = required.type_name
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'Ingestion provenance has missing/incompatible column: ' || required.column_name;
        END IF;
    END LOOP;
END $$;

COMMIT;
