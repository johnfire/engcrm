-- Personal priority gains 6 "Forget it" below 5 "Not now". Only organizations
-- (contact_user_priorities); a person's contact-value rating stays 1-5.
ALTER TABLE contact_user_priorities DROP CONSTRAINT IF EXISTS contact_user_priorities_priority_check;
ALTER TABLE contact_user_priorities
    ADD CONSTRAINT contact_user_priorities_priority_check CHECK (priority BETWEEN 1 AND 6);
