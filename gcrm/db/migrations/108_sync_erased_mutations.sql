ALTER TABLE sync_mutations DROP CONSTRAINT sync_mutations_status_check;
ALTER TABLE sync_mutations ADD CONSTRAINT sync_mutations_status_check CHECK (status IN
    ('applied', 'partially_applied', 'ignored_older', 'provisional', 'rejected_validation', 'rejected_clock', 'erased'));
