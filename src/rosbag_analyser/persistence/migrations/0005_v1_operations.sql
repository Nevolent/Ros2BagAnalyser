CREATE TABLE IF NOT EXISTS catalog_state (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    successful_generation BIGINT NOT NULL CHECK (successful_generation >= 0),
    successful_completed_at TIMESTAMPTZ,
    duration_ms BIGINT NOT NULL CHECK (duration_ms >= 0),
    recording_count BIGINT NOT NULL CHECK (recording_count >= 0),
    readable_count BIGINT NOT NULL CHECK (readable_count >= 0),
    damaged_count BIGINT NOT NULL CHECK (damaged_count >= 0),
    missing_count BIGINT NOT NULL CHECK (missing_count >= 0),
    unsupported_count BIGINT NOT NULL CHECK (unsupported_count >= 0),
    uninspectable_count BIGINT NOT NULL CHECK (uninspectable_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (successful_generation = 0 AND successful_completed_at IS NULL)
        OR (successful_generation > 0 AND successful_completed_at IS NOT NULL)
    )
);

INSERT INTO catalog_state (
    singleton, successful_generation, successful_completed_at, duration_ms,
    recording_count, readable_count, damaged_count, missing_count,
    unsupported_count, uninspectable_count
) SELECT
    TRUE,
    0,
    NULL,
    0,
    count(*),
    count(*) FILTER (WHERE ros_health = 'readable'),
    count(*) FILTER (WHERE ros_health = 'damaged'),
    count(*) FILTER (WHERE ros_health = 'missing'),
    count(*) FILTER (WHERE ros_health = 'unsupported'),
    count(*) FILTER (WHERE ros_health = 'uninspectable')
FROM recordings
ON CONFLICT (singleton) DO NOTHING;

ALTER TABLE recordings
    ADD COLUMN IF NOT EXISTS source_present BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE recordings
    ADD COLUMN IF NOT EXISTS last_seen_generation BIGINT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'recordings'::regclass
          AND conname = 'recordings_last_seen_generation_check'
    ) THEN
        ALTER TABLE recordings
            ADD CONSTRAINT recordings_last_seen_generation_check
            CHECK (last_seen_generation >= 0);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS preparation_targets (
    recording_id BIGINT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (
        kind IN ('front_preview', 'topdown_preview', 'imu_series')
    ),
    scan_generation BIGINT NOT NULL CHECK (scan_generation >= 0),
    planner_identity TEXT NOT NULL CHECK (char_length(planner_identity) = 64),
    target_state TEXT NOT NULL CHECK (
        target_state IN ('available', 'unavailable')
    ),
    cache_identity TEXT CHECK (
        cache_identity IS NULL OR char_length(cache_identity) = 64
    ),
    diagnostic_code TEXT,
    diagnostic_message TEXT CHECK (
        diagnostic_message IS NULL OR char_length(diagnostic_message) <= 500
    ),
    work_units BIGINT CHECK (work_units IS NULL OR work_units > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recording_id, kind),
    CHECK (
        (
            target_state = 'available'
            AND cache_identity IS NOT NULL
            AND work_units IS NOT NULL
            AND diagnostic_code IS NULL
            AND diagnostic_message IS NULL
        )
        OR (
            target_state = 'unavailable'
            AND cache_identity IS NULL
            AND work_units IS NULL
            AND diagnostic_code IS NOT NULL
            AND diagnostic_message IS NOT NULL
        )
    )
);

INSERT INTO preparation_targets (
    recording_id, kind, scan_generation, planner_identity, target_state,
    cache_identity, diagnostic_code, diagnostic_message, work_units
)
SELECT recording.id,
       kind.value,
       0,
       repeat('0', 64),
       'unavailable',
       NULL,
       'catalog_rescan_required',
       'Preparation targets require an explicit catalog rescan.',
       NULL
FROM recordings AS recording
CROSS JOIN (
    VALUES ('front_preview'), ('topdown_preview'), ('imu_series')
) AS kind(value)
ON CONFLICT (recording_id, kind) DO NOTHING;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS work_units BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS estimate_key TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS estimated_total_ms BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS estimate_method TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS estimate_sample_count INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'jobs'::regclass
          AND conname = 'jobs_v1_estimate_check'
    ) THEN
        ALTER TABLE jobs
            ADD CONSTRAINT jobs_v1_estimate_check
            CHECK (
                (
                    work_units IS NULL
                    AND estimate_key IS NULL
                    AND estimated_total_ms IS NULL
                    AND estimate_method IS NULL
                    AND estimate_sample_count IS NULL
                )
                OR (
                    work_units > 0
                    AND char_length(estimate_key) = 64
                    AND (
                        (
                            estimated_total_ms IS NULL
                            AND estimate_method IS NULL
                            AND estimate_sample_count IS NULL
                        )
                        OR (
                            estimated_total_ms > 0
                            AND estimate_method = 'median_rate_v1'
                            AND estimate_sample_count >= 2
                        )
                        OR (
                            estimated_total_ms IS NULL
                            AND estimate_method = 'insufficient_history'
                            AND estimate_sample_count BETWEEN 0 AND 1
                        )
                    )
                )
            );
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_running_globally
    ON jobs ((TRUE))
    WHERE state = 'running';

CREATE INDEX IF NOT EXISTS preparation_targets_current_identity
    ON preparation_targets (kind, cache_identity, recording_id)
    WHERE target_state = 'available';

CREATE INDEX IF NOT EXISTS jobs_actionable_failure
    ON jobs (kind, cache_identity, finished_at DESC, id DESC)
    WHERE state = 'failed';

CREATE INDEX IF NOT EXISTS jobs_succeeded_history
    ON jobs (finished_at DESC, id DESC)
    WHERE state = 'succeeded';

CREATE INDEX IF NOT EXISTS jobs_estimation_samples
    ON jobs (estimate_key, finished_at DESC, id DESC)
    WHERE state = 'succeeded' AND work_units IS NOT NULL;
