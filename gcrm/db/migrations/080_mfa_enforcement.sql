-- Pending enrollment never enables a factor until a current code is proved.
ALTER TABLE users ADD COLUMN mfa_pending_secret TEXT;
ALTER TABLE users ADD COLUMN mfa_pending_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN mfa_last_counter BIGINT NOT NULL DEFAULT -1;
ALTER TABLE users ADD COLUMN mfa_recovery_hashes TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE users ADD COLUMN mfa_failed_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mfa_blocked_until TIMESTAMPTZ;
