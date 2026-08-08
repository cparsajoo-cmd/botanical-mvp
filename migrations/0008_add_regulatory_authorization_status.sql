-- Canonical regulatory authorization state persistence.
ALTER TABLE evidence_records
ADD COLUMN IF NOT EXISTS regulatory_authorization_status TEXT;

COMMENT ON COLUMN evidence_records.regulatory_authorization_status IS
'Structured authorization state for the matched jurisdiction/product context: authorized, not_authorized, pending, denied, terminated, unknown.';
