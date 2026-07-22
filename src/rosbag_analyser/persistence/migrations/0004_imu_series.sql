DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%imu_series%'
    ) THEN
        ALTER TABLE artifacts DROP CONSTRAINT artifacts_kind_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'artifacts'::regclass
          AND conname = 'artifacts_kind_check'
    ) THEN
        ALTER TABLE artifacts
            ADD CONSTRAINT artifacts_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series'));
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
          AND pg_get_constraintdef(oid, true) NOT LIKE '%imu_series%'
    ) THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_kind_check'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT jobs_kind_check
            CHECK (kind IN ('front_preview', 'topdown_preview', 'imu_series'));
    END IF;
END
$$;
