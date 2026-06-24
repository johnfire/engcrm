-- Per-user token version for mobile JWT revocation. Bumping it (on account
-- deactivation or password reset) invalidates that user's outstanding bearer
-- tokens, so a disabled user or a reset password takes effect immediately
-- instead of lingering for up to the 24h token lifetime.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
