ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS control_state TEXT NOT NULL DEFAULT 'none';

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS execution_phase TEXT;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS control_revision BIGINT NOT NULL DEFAULT 0;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS last_pause_requested_at TIMESTAMPTZ;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS last_pause_acknowledged_at TIMESTAMPTZ;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS last_resumed_at TIMESTAMPTZ;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS accumulated_paused_ms BIGINT NOT NULL DEFAULT 0;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMPTZ;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS cancel_finished_at TIMESTAMPTZ;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS queue_order BIGINT;

CREATE SEQUENCE IF NOT EXISTS jobs_queue_order_seq;

WITH ordered AS (
    SELECT id, row_number() OVER (ORDER BY queued_at, id) AS position
    FROM jobs
)
UPDATE jobs
SET queue_order = ordered.position
FROM ordered
WHERE jobs.id = ordered.id
  AND jobs.queue_order IS NULL;

SELECT setval(
    'jobs_queue_order_seq',
    GREATEST(COALESCE((SELECT max(queue_order) FROM jobs), 0) + 1, 1),
    FALSE
);

ALTER SEQUENCE jobs_queue_order_seq OWNED BY jobs.queue_order;

ALTER TABLE jobs
    ALTER COLUMN queue_order SET DEFAULT nextval('jobs_queue_order_seq');

ALTER TABLE jobs
    ALTER COLUMN queue_order SET NOT NULL;

UPDATE jobs
SET execution_phase = 'setup'
WHERE state = 'running' AND execution_phase IS NULL;

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_state_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_check1;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_control_values_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_lifecycle_shape_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_control_shape_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_error_shape_check;

ALTER TABLE jobs
    ADD CONSTRAINT jobs_state_check CHECK (
        state IN ('queued', 'running', 'succeeded', 'failed', 'canceled')
    );

ALTER TABLE jobs
    ADD CONSTRAINT jobs_control_values_check CHECK (
        control_state IN ('none', 'pause_requested', 'paused', 'cancel_requested')
        AND (
            execution_phase IS NULL
            OR execution_phase IN (
                'setup', 'processing', 'validating', 'publishing', 'cleanup'
            )
        )
        AND control_revision >= 0
        AND accumulated_paused_ms >= 0
        AND queue_order > 0
    );

ALTER TABLE jobs
    ADD CONSTRAINT jobs_lifecycle_shape_check CHECK (
        (
            state = 'queued'
            AND started_at IS NULL
            AND finished_at IS NULL
            AND control_state = 'none'
            AND execution_phase IS NULL
            AND cancel_requested_at IS NULL
            AND cancel_finished_at IS NULL
        )
        OR (
            state = 'running'
            AND started_at IS NOT NULL
            AND finished_at IS NULL
            AND execution_phase IS NOT NULL
            AND cancel_finished_at IS NULL
        )
        OR (
            state IN ('succeeded', 'failed')
            AND started_at IS NOT NULL
            AND finished_at IS NOT NULL
            AND control_state = 'none'
            AND execution_phase IS NULL
            AND cancel_finished_at IS NULL
        )
        OR (
            state = 'canceled'
            AND finished_at IS NOT NULL
            AND control_state = 'none'
            AND execution_phase IS NULL
            AND cancel_requested_at IS NOT NULL
            AND cancel_finished_at IS NOT NULL
        )
    );

ALTER TABLE jobs
    ADD CONSTRAINT jobs_control_shape_check CHECK (
        (control_state <> 'pause_requested' OR last_pause_requested_at IS NOT NULL)
        AND (control_state <> 'paused' OR last_pause_acknowledged_at IS NOT NULL)
        AND (control_state <> 'cancel_requested' OR cancel_requested_at IS NOT NULL)
        AND (
            control_state NOT IN ('pause_requested', 'paused', 'cancel_requested')
            OR state = 'running'
        )
        AND (
            control_state <> 'paused'
            OR last_pause_acknowledged_at >= last_pause_requested_at
        )
        AND (
            started_at IS NULL
            OR finished_at IS NULL
            OR finished_at >= started_at
        )
        AND (
            cancel_finished_at IS NULL
            OR cancel_finished_at >= cancel_requested_at
        )
    );

ALTER TABLE jobs
    ADD CONSTRAINT jobs_error_shape_check CHECK (
        (state = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL)
        OR (state <> 'failed' AND error_code IS NULL AND error_message IS NULL)
    );

DROP INDEX IF EXISTS jobs_queue_order;
CREATE INDEX jobs_queue_order
    ON jobs (queue_order, id)
    WHERE state = 'queued';

CREATE INDEX IF NOT EXISTS jobs_canceled_history
    ON jobs (finished_at DESC, id DESC)
    WHERE state = 'canceled';
