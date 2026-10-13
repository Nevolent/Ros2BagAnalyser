-- Keep historical predictions intact while admitting the comparable-input policy.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_v1_estimate_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_v1_estimate_check CHECK (
    (work_units IS NULL AND estimate_key IS NULL AND estimated_total_ms IS NULL
        AND estimate_method IS NULL AND estimate_sample_count IS NULL)
    OR (work_units > 0 AND char_length(estimate_key) = 64 AND (
        (estimated_total_ms IS NULL AND estimate_method IS NULL AND estimate_sample_count IS NULL)
        OR (estimated_total_ms > 0
            AND estimate_method IN ('median_rate_v1', 'recent_rate_v2', 'recent_rate_v3')
            AND estimate_sample_count >= 2)
        OR (estimated_total_ms IS NULL AND estimate_method = 'insufficient_history'
            AND estimate_sample_count BETWEEN 0 AND 1)
    ))
);
