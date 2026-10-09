-- Add single-frame thumbnails without touching sources or creating work during upgrade.
DO $$
DECLARE
    table_name text;
    constraint_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['artifacts', 'jobs', 'preparation_targets'] LOOP
        constraint_name := table_name || '_kind_check';
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_constraint
            WHERE conrelid = table_name::regclass AND conname = constraint_name
              AND pg_get_constraintdef(oid, true) NOT LIKE '%thumbnail%'
        ) THEN
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', table_name, constraint_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_constraint
            WHERE conrelid = table_name::regclass AND conname = constraint_name
        ) THEN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I CHECK (kind IN '
                || '(''front_preview'', ''topdown_preview'', ''imu_series'', '
                || '''ai_description'', ''encoder_series'', ''thumbnail''))', table_name, constraint_name);
        END IF;
    END LOOP;
END
$$;

INSERT INTO preparation_targets (
    recording_id, kind, scan_generation, planner_identity, target_state,
    cache_identity, diagnostic_code, diagnostic_message, work_units
)
SELECT recording_id, 'thumbnail', scan_generation,
       encode(sha256(convert_to('thumbnail-v1:default-colour:record-midpoint:side480:png', 'UTF8')), 'hex'),
       target_state,
       CASE WHEN cache_identity IS NULL THEN NULL ELSE
           encode(sha256(convert_to(cache_identity || ':' ||
               'thumbnail-v1:default-colour:record-midpoint:side480:png', 'UTF8')), 'hex') END,
       diagnostic_code, diagnostic_message,
       CASE WHEN target_state = 'available' THEN 1 ELSE NULL END
FROM preparation_targets WHERE kind = 'front_preview'
ON CONFLICT (recording_id, kind) DO NOTHING;
