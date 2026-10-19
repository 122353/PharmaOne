-- PharmaOne AI: pharmacy-scoped regulatory notifications.
-- Apply with a PostgreSQL migration role after taking the normal database backup.
-- This migration is additive and repeatable for a compatible existing schema.

BEGIN;

CREATE TABLE IF NOT EXISTS public.monitoring_notifications (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    event_id VARCHAR(64) NOT NULL,
    inventory_id VARCHAR(36) NOT NULL REFERENCES public.inventory_items(id),
    alert_id VARCHAR(64) NOT NULL REFERENCES public.regulatory_alerts(fingerprint),
    status VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_monitoring_notification_event UNIQUE (pharmacy_id, event_id)
);

-- Handles a notification table created by an earlier local prototype.
ALTER TABLE public.monitoring_notifications
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- IF NOT EXISTS does not establish constraints on a pre-existing table. Refuse
-- incompatible prototypes transactionally rather than silently accepting them
-- or guessing how existing duplicates/orphans should be repaired.
DO $$
DECLARE
    required RECORD;
    column_number SMALLINT;
    reference_number SMALLINT;
    pharmacy_number SMALLINT;
    event_number SMALLINT;
BEGIN
    FOR required IN SELECT * FROM (VALUES
        ('id', 'character varying(36)'),
        ('pharmacy_id', 'character varying(36)'),
        ('event_id', 'character varying(64)'),
        ('inventory_id', 'character varying(36)'),
        ('alert_id', 'character varying(64)'),
        ('status', 'character varying(32)'),
        ('title', 'character varying(255)'),
        ('message', 'text'),
        ('is_read', 'boolean'),
        ('is_active', 'boolean'),
        ('created_at', 'timestamp with time zone')
    ) AS columns(column_name, type_name)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_attribute a
            WHERE a.attrelid = 'public.monitoring_notifications'::regclass
              AND a.attname = required.column_name AND NOT a.attisdropped
              AND a.attnotnull AND format_type(a.atttypid, a.atttypmod) = required.type_name
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'Notification prototype has missing/incompatible column: ' || required.column_name;
        END IF;
    END LOOP;

    SELECT attnum INTO column_number FROM pg_attribute
        WHERE attrelid = 'public.monitoring_notifications'::regclass AND attname = 'id';
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conrelid = 'public.monitoring_notifications'::regclass
          AND contype = 'p' AND convalidated AND conkey = ARRAY[column_number]
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Notification prototype requires a primary key on id';
    END IF;

    FOR required IN SELECT * FROM (VALUES
        ('pharmacy_id', 'public.pharmacies', 'id'),
        ('inventory_id', 'public.inventory_items', 'id'),
        ('alert_id', 'public.regulatory_alerts', 'fingerprint')
    ) AS foreign_keys(column_name, target_table, target_column)
    LOOP
        SELECT attnum INTO column_number FROM pg_attribute
            WHERE attrelid = 'public.monitoring_notifications'::regclass AND attname = required.column_name;
        SELECT attnum INTO reference_number FROM pg_attribute
            WHERE attrelid = required.target_table::regclass AND attname = required.target_column;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conrelid = 'public.monitoring_notifications'::regclass
              AND contype = 'f' AND convalidated AND conkey = ARRAY[column_number]
              AND confrelid = required.target_table::regclass AND confkey = ARRAY[reference_number]
              AND confdeltype = 'a' AND confupdtype = 'a'
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'Notification prototype requires a validated foreign key: ' || required.column_name;
        END IF;
    END LOOP;

    SELECT attnum INTO pharmacy_number FROM pg_attribute
        WHERE attrelid = 'public.monitoring_notifications'::regclass AND attname = 'pharmacy_id';
    SELECT attnum INTO event_number FROM pg_attribute
        WHERE attrelid = 'public.monitoring_notifications'::regclass AND attname = 'event_id';
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conrelid = 'public.monitoring_notifications'::regclass
          AND contype = 'u' AND convalidated
          AND (conkey = ARRAY[pharmacy_number, event_number] OR conkey = ARRAY[event_number, pharmacy_number])
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Notification prototype requires unique (pharmacy_id, event_id)';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_monitoring_notifications_pharmacy_id
    ON public.monitoring_notifications (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_monitoring_notifications_pharmacy_active_created
    ON public.monitoring_notifications (pharmacy_id, is_active, created_at);
CREATE INDEX IF NOT EXISTS ix_monitoring_notifications_pharmacy_unread_active
    ON public.monitoring_notifications (pharmacy_id, is_active, is_read);

-- An unrelated or incorrectly shaped index can also occupy an IF NOT EXISTS
-- name. Verify the actual indexed columns and reject partial/expression indexes.
DO $$
DECLARE required RECORD;
BEGIN
    FOR required IN SELECT * FROM (VALUES
        ('ix_monitoring_notifications_pharmacy_id', ARRAY['pharmacy_id']::TEXT[]),
        ('ix_monitoring_notifications_pharmacy_active_created', ARRAY['pharmacy_id', 'is_active', 'created_at']::TEXT[]),
        ('ix_monitoring_notifications_pharmacy_unread_active', ARRAY['pharmacy_id', 'is_active', 'is_read']::TEXT[])
    ) AS indexes(index_name, column_names)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_index i JOIN pg_class idx ON idx.oid = i.indexrelid
            WHERE i.indrelid = 'public.monitoring_notifications'::regclass
              AND idx.relname = required.index_name AND i.indisvalid AND i.indisready
              AND i.indpred IS NULL AND i.indexprs IS NULL
              AND ARRAY(
                  SELECT a.attname::TEXT FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
                  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                  ORDER BY k.position
              ) = required.column_names
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'Notification prototype has an incompatible index: ' || required.index_name;
        END IF;
    END LOOP;
END $$;

ALTER TABLE public.monitoring_notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.monitoring_notifications FROM PUBLIC;

DO $$
DECLARE role_name TEXT;
BEGIN
    FOR role_name IN
        SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.monitoring_notifications FROM %I', role_name);
    END LOOP;
END $$;

COMMIT;
