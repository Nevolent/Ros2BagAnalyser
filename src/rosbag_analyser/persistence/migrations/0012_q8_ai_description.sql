-- Refresh only AI targets from saved front identities. Preserve artifacts and jobs;
-- an explicit Prepare Selected generates descriptions under the new CPU policy.
INSERT INTO preparation_targets (
    recording_id, kind, scan_generation, planner_identity, target_state,
    cache_identity, diagnostic_code, diagnostic_message, work_units
)
SELECT recording_id, 'ai_description', scan_generation,
       '3171b7da6256dc536d89a1cebfdb3d544677f5e68dd259260b8e709eb4bd3278', target_state,
       CASE WHEN cache_identity IS NULL THEN NULL
            ELSE encode(sha256(convert_to(cache_identity || ':' ||
                 'ai-description-v2:qwen3-vl-2b-q8-52d6c8ff-llama-8345f333-cpu-v1:ordered-images:frames6:side448:tokens160:prompt-v1:formatter-v1', 'UTF8')), 'hex') END,
       diagnostic_code, diagnostic_message, work_units
FROM preparation_targets WHERE kind = 'front_preview'
ON CONFLICT (recording_id, kind) DO UPDATE SET
    scan_generation = EXCLUDED.scan_generation,
    planner_identity = EXCLUDED.planner_identity,
    target_state = EXCLUDED.target_state,
    cache_identity = EXCLUDED.cache_identity,
    diagnostic_code = EXCLUDED.diagnostic_code,
    diagnostic_message = EXCLUDED.diagnostic_message,
    work_units = EXCLUDED.work_units
-- Migrations may be replayed: do not downgrade a later planner or refresh
-- already-current targets. Only the known pre-Q8 policy needs replacement.
WHERE preparation_targets.planner_identity =
    'ac1caef9b5d65940f1fc528209d7f6a3df9984a361967b1ce583ff9b825d5304';
