-- Saved topic inventory and bounded timing inspection, refreshed by explicit scan.
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS scan_details JSONB;
