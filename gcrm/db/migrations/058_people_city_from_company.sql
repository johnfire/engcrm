-- Migration 058: a person with no city lives where their company is.
--
-- People arrive without a city (LinkedIn's Connections.csv has no location),
-- and companies get theirs later, from several places (Places lookup, website
-- lookup, the review page, a hand edit). Two triggers keep the rule in one place
-- whichever path does the writing:
--
--   people   BEFORE INSERT / UPDATE OF contact_id
--            a person with a blank city takes the company's city and country
--            when they are created with, or linked to, a company.
--   contacts AFTER UPDATE OF city
--            when a company's city changes, linked people with a blank city
--            take it.
--
-- A city that is already set is never overwritten: it came from a business card
-- or was typed in, which is evidence the person works elsewhere. Clearing a
-- person's city by hand also sticks until their company link or the company's
-- city changes. Existing blanks are filled once by
-- scripts/people_city_from_company.py, not here, so they can be previewed.

CREATE OR REPLACE FUNCTION people_city_from_company() RETURNS trigger AS $$
DECLARE
    company RECORD;
BEGIN
    IF NEW.contact_id IS NOT NULL AND COALESCE(TRIM(NEW.city), '') = '' THEN
        SELECT city, country INTO company
          FROM contacts WHERE id = NEW.contact_id AND deleted_at IS NULL;
        IF COALESCE(TRIM(company.city), '') <> '' THEN
            NEW.city := TRIM(company.city);
            NEW.country := COALESCE(NULLIF(TRIM(company.country), ''), NEW.country);
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS people_city_from_company ON people;
CREATE TRIGGER people_city_from_company
    BEFORE INSERT OR UPDATE OF contact_id ON people
    FOR EACH ROW EXECUTE FUNCTION people_city_from_company();

CREATE OR REPLACE FUNCTION company_city_to_people() RETURNS trigger AS $$
BEGIN
    IF COALESCE(TRIM(NEW.city), '') <> '' AND NEW.deleted_at IS NULL THEN
        UPDATE people
           SET city = TRIM(NEW.city),
               country = COALESCE(NULLIF(TRIM(NEW.country), ''), country),
               updated_at = NOW()
         WHERE contact_id = NEW.id
           AND deleted_at IS NULL
           AND COALESCE(TRIM(city), '') = '';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS company_city_to_people ON contacts;
CREATE TRIGGER company_city_to_people
    AFTER UPDATE OF city ON contacts
    FOR EACH ROW WHEN (NEW.city IS DISTINCT FROM OLD.city)
    EXECUTE FUNCTION company_city_to_people();
