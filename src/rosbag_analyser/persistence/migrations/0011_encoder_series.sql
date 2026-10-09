-- New optional output. An explicit rescan discovers its source topic and identity.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%encoder_series%'
    ) THEN
        ALTER TABLE artifacts DROP CONSTRAINT artifacts_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
    ) THEN
        ALTER TABLE artifacts ADD CONSTRAINT artifacts_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description', 'encoder_series'));
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%encoder_series%'
    ) THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description', 'encoder_series'));
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'preparation_targets'::regclass
          AND conname = 'preparation_targets_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%encoder_series%'
    ) THEN
        ALTER TABLE preparation_targets DROP CONSTRAINT preparation_targets_kind_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'preparation_targets'::regclass
          AND conname = 'preparation_targets_kind_check'
    ) THEN
        ALTER TABLE preparation_targets ADD CONSTRAINT preparation_targets_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series', 'ai_description', 'encoder_series'));
    END IF;
END
$$;
