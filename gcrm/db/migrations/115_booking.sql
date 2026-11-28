-- Migration 115: booking. People pick a free time on a public page; engcrm sends both sides a calendar
-- invite. See docs/plans/2026-11-28-booking-design.md. Safe to run twice: every statement checks what is
-- already there.

CREATE TABLE IF NOT EXISTS booking_settings (
    workspace_id        INTEGER PRIMARY KEY DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    is_enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    public_slug         TEXT UNIQUE CHECK (public_slug ~ '^[a-z0-9][a-z0-9-]{1,39}$'),
    -- Proton "Share with anyone" link; it carries the calendar's decryption key, so it is stored encrypted.
    feed_url_encrypted  TEXT,
    organizer_email     TEXT NOT NULL DEFAULT '' CHECK (length(organizer_email) <= 254),
    organizer_name      TEXT NOT NULL DEFAULT '' CHECK (length(organizer_name) <= 200),
    host_email          TEXT NOT NULL DEFAULT '' CHECK (length(host_email) <= 254),
    room_link           TEXT NOT NULL DEFAULT '' CHECK (room_link = '' OR (room_link ~* '^https://' AND length(room_link) <= 2000)),
    time_zone           TEXT NOT NULL DEFAULT 'Europe/Berlin',
    min_notice_hours    INTEGER NOT NULL DEFAULT 24 CHECK (min_notice_hours BETWEEN 0 AND 720),
    horizon_days        INTEGER NOT NULL DEFAULT 42 CHECK (horizon_days BETWEEN 1 AND 365),
    gap_minutes         INTEGER NOT NULL DEFAULT 15 CHECK (gap_minutes BETWEEN 0 AND 240),
    cancel_cutoff_hours INTEGER NOT NULL DEFAULT 12 CHECK (cancel_cutoff_hours BETWEEN 0 AND 720),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Kinds: call, video, visit, custom. Names come from the translations by kind.
CREATE TABLE IF NOT EXISTS booking_types (
    id             SERIAL PRIMARY KEY,
    workspace_id   INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL CHECK (kind IN ('call', 'video', 'visit', 'custom')),
    minutes        INTEGER NOT NULL CHECK (minutes BETWEEN 5 AND 480),
    travel_minutes INTEGER NOT NULL DEFAULT 0 CHECK (travel_minutes BETWEEN 0 AND 480),
    -- 0 = Monday. NULL = every day with open hours.
    weekdays       INTEGER[] CHECK (weekdays IS NULL OR weekdays <@ ARRAY[0,1,2,3,4,5,6]),
    needs_approval BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (workspace_id, kind)
);

CREATE TABLE IF NOT EXISTS booking_hours (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    weekday      INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    opens        TIME NOT NULL,
    closes       TIME NOT NULL CHECK (closes > opens)
);
CREATE INDEX IF NOT EXISTS idx_booking_hours_workspace ON booking_hours (workspace_id, weekday, opens);

-- Time Chris blocks by hand, for events Proton's share link shows late (up to 8 hours).
CREATE TABLE IF NOT EXISTS booking_blocks (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    starts_at    TIMESTAMPTZ NOT NULL,
    ends_at      TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
    note         TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 200)
);
CREATE INDEX IF NOT EXISTS idx_booking_blocks_time ON booking_blocks (workspace_id, ends_at);

-- Personal links: the token names who is booking, so those bookings link and confirm at once.
CREATE TABLE IF NOT EXISTS booking_links (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    token_encrypted TEXT NOT NULL,
    label           TEXT NOT NULL CHECK (length(trim(label)) > 0 AND length(label) <= 200),
    contact_id      INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    person_id       INTEGER REFERENCES people(id) ON DELETE CASCADE,
    deal_id         INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    kinds           TEXT[] NOT NULL DEFAULT ARRAY['call','video','visit','custom'],
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (contact_id IS NOT NULL OR person_id IS NOT NULL)
);

-- held: public booking waiting for its confirm click until hold_expires_at.
-- requested: custom booking waiting for Chris. confirmed / declined / cancelled are final states,
-- except that a confirmed booking can move (new times, sequence + 1).
-- occupied_* is the span the booking blocks, travel and gap included (gcrm/booking/slots.py).
CREATE TABLE IF NOT EXISTS bookings (
    id                  SERIAL PRIMARY KEY,
    workspace_id        INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    booking_type_id     INTEGER NOT NULL REFERENCES booking_types(id),
    link_id             INTEGER REFERENCES booking_links(id) ON DELETE SET NULL,
    status              TEXT NOT NULL CHECK (status IN ('held', 'requested', 'confirmed', 'declined', 'cancelled')),
    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
    occupied_from       TIMESTAMPTZ NOT NULL CHECK (occupied_from <= starts_at),
    occupied_until      TIMESTAMPTZ NOT NULL CHECK (occupied_until >= ends_at),
    hold_expires_at     TIMESTAMPTZ,
    guest_name          TEXT NOT NULL CHECK (length(trim(guest_name)) > 0 AND length(guest_name) <= 200),
    guest_email         TEXT NOT NULL CHECK (guest_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' AND length(guest_email) <= 254),
    company             TEXT NOT NULL DEFAULT '' CHECK (length(company) <= 200),
    topic               TEXT NOT NULL DEFAULT '' CHECK (length(topic) <= 2000),
    visit_address       TEXT NOT NULL DEFAULT '' CHECK (length(visit_address) <= 500),
    phone               TEXT NOT NULL DEFAULT '' CHECK (length(phone) <= 40),
    language            TEXT NOT NULL DEFAULT 'de' CHECK (language IN ('de', 'en')),
    ics_uid             TEXT NOT NULL UNIQUE,
    sequence            INTEGER NOT NULL DEFAULT 0,
    confirm_token_hash  TEXT UNIQUE,
    manage_token_hash   TEXT NOT NULL UNIQUE,
    -- Kept encrypted so later emails (approved, moved, cancelled) can carry the manage link again.
    manage_token_encrypted TEXT NOT NULL,
    contact_id          INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    person_id           INTEGER REFERENCES people(id) ON DELETE SET NULL,
    deal_id             INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    follow_up_id        BIGINT REFERENCES follow_ups(id) ON DELETE SET NULL,
    invite_sent_at      TIMESTAMPTZ,
    activity_logged_at  TIMESTAMPTZ,
    invite_error        TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((status = 'held') = (hold_expires_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_bookings_occupied ON bookings (workspace_id, occupied_until)
    WHERE status IN ('held', 'requested', 'confirmed');
CREATE INDEX IF NOT EXISTS idx_bookings_guest ON bookings (workspace_id, lower(guest_email));

-- Row security like every other table (pattern of migration 111).
DO $$
DECLARE booking_table TEXT;
BEGIN
    FOREACH booking_table IN ARRAY ARRAY['booking_settings','booking_types','booking_hours','booking_blocks',
                                         'booking_links','bookings']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', booking_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', booking_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', booking_table || '_workspace', booking_table);
        EXECUTE format('CREATE POLICY %I ON %I TO engcrm_workspace '
                       'USING (workspace_id = request_workspace_id()) '
                       'WITH CHECK (workspace_id = request_workspace_id())',
                       booking_table || '_workspace', booking_table);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO engcrm_workspace', booking_table);
    END LOOP;
END $$;
GRANT USAGE, SELECT ON SEQUENCE booking_types_id_seq, booking_hours_id_seq, booking_blocks_id_seq,
    booking_links_id_seq, bookings_id_seq TO engcrm_workspace;

-- The public page has no login, so it learns its workspace from the slug before any workspace is set.
-- That phase may read only these three columns, and only of enabled pages (pattern of migration 081).
GRANT SELECT (workspace_id, public_slug, is_enabled) ON booking_settings TO engcrm_app;
DROP POLICY IF EXISTS runtime_booking_page_lookup ON booking_settings;
CREATE POLICY runtime_booking_page_lookup ON booking_settings FOR SELECT TO engcrm_app USING (is_enabled);
