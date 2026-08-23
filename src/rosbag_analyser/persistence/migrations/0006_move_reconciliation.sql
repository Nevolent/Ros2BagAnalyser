ALTER TABLE recordings
    ADD COLUMN IF NOT EXISTS cache_identity_recording_id BIGINT;

ALTER TABLE recordings
    ADD COLUMN IF NOT EXISTS cache_identity_relative_path TEXT;

ALTER TABLE recordings
    ADD COLUMN IF NOT EXISTS move_fingerprint TEXT;

UPDATE recordings
SET cache_identity_recording_id = id,
    cache_identity_relative_path = archive_relative_path
WHERE cache_identity_recording_id IS NULL
   OR cache_identity_relative_path IS NULL;

ALTER TABLE recordings
    ALTER COLUMN cache_identity_recording_id SET NOT NULL;

ALTER TABLE recordings
    ALTER COLUMN cache_identity_relative_path SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'recordings'::regclass
          AND conname = 'recordings_cache_identity_recording_id_check'
    ) THEN
        ALTER TABLE recordings
            ADD CONSTRAINT recordings_cache_identity_recording_id_check
            CHECK (cache_identity_recording_id > 0);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'recordings'::regclass
          AND conname = 'recordings_cache_identity_relative_path_check'
    ) THEN
        ALTER TABLE recordings
            ADD CONSTRAINT recordings_cache_identity_relative_path_check
            CHECK (cache_identity_relative_path <> '');
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'recordings'::regclass
          AND conname = 'recordings_move_fingerprint_check'
    ) THEN
        ALTER TABLE recordings
            ADD CONSTRAINT recordings_move_fingerprint_check
            CHECK (
                move_fingerprint IS NULL
                OR char_length(move_fingerprint) = 64
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS recordings_move_fingerprint
    ON recordings (move_fingerprint, source_present, last_seen_generation DESC, id)
    WHERE move_fingerprint IS NOT NULL;
