-- deals.next_step / next_step_date show a deal's earliest active follow-up, but they could fall behind: until
-- this release an activity promise did not refresh them. Bring the live deals that have an active follow-up
-- up to date, in the order the application uses (dated first, then undated, ID as tie-breaker). A deal with no
-- active follow-up keeps whatever it shows, and a deal already right is not written, so running this again
-- changes nothing. A function so a test can run the same code on seeded rows (like 111); the operator running
-- the migration is not subject to row security. Returns how many deals it changed.
CREATE OR REPLACE FUNCTION reproject_deal_next_steps() RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    changed INTEGER;
BEGIN
    UPDATE deals d SET next_step = earliest.task_text, next_step_date = earliest.due_date
      FROM (SELECT DISTINCT ON (deal_id) deal_id, task_text, due_date
              FROM follow_ups
             WHERE status = 'active' AND deal_id IS NOT NULL
             ORDER BY deal_id, due_date ASC NULLS LAST, id) AS earliest
     WHERE d.id = earliest.deal_id AND d.deleted_at IS NULL
       AND (d.next_step, d.next_step_date) IS DISTINCT FROM (earliest.task_text, earliest.due_date);
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END $$;
REVOKE ALL ON FUNCTION reproject_deal_next_steps() FROM PUBLIC;

SELECT reproject_deal_next_steps();
