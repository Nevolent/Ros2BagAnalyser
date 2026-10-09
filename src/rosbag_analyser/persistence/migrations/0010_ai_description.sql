DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%ai_description%'
    ) THEN
        ALTER TABLE artifacts DROP CONSTRAINT artifacts_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
    ) THEN
        ALTER TABLE artifacts ADD CONSTRAINT artifacts_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description'));
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%ai_description%'
    ) THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description'));
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'preparation_targets'::regclass
          AND conname = 'preparation_targets_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%ai_description%'
    ) THEN
        ALTER TABLE preparation_targets DROP CONSTRAINT preparation_targets_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'preparation_targets'::regclass
          AND conname = 'preparation_targets_kind_check'
    ) THEN
        ALTER TABLE preparation_targets ADD CONSTRAINT preparation_targets_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description'));
    END IF;
END
$$;

-- Derive the new target from saved front facts; never access or rewrite source data.
INSERT INTO preparation_targets (
    recording_id, kind, scan_generation, planner_identity, target_state,
    cache_identity, diagnostic_code, diagnostic_message, work_units
)
SELECT recording_id, 'ai_description', scan_generation,
       'ac1caef9b5d65940f1fc528209d7f6a3df9984a361967b1ce583ff9b825d5304', target_state,
       CASE WHEN cache_identity IS NULL THEN NULL
            ELSE encode(sha256(convert_to(cache_identity || ':' ||
                 'ai-description-v1:qwen3-vl-2b-89644892e4d85e24eaac8bacfd4f463576704203:frames12:side640:tokens160', 'UTF8')), 'hex') END,
       diagnostic_code, diagnostic_message, work_units
FROM preparation_targets WHERE kind = 'front_preview'
ON CONFLICT (recording_id, kind) DO NOTHING;
