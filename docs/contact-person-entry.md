# Adding a company contact on the website

Open an organization and choose **Add contact person**. The Add person form
already selects that company. The normal Add person page also has a Company
selector, so a person can be linked while they are created.

For someone already saved, search by name in **Find someone already saved** on
the company-specific form and choose **Use this contact person**. Only people
without a company, or already at the chosen company, are offered. This flow does
not move people away from another company.

Check **I spoke to this person in person today** only when that happened. Saving
then records one drop-in on the person as well as their company link, so the
Contacts page includes them under the business. Leaving it unchecked saves their
details without inventing contact history or a sales deal. A pipeline-filtered
People list still shows only people pitched the selected offer; choose **All
offers** to see everyone.

A successful save opens the person's details with **Saved.** and a company link.
Duplicates open a warning with a link to the existing person. Validation and save
failures retain the entered fields. Creation/linking and the optional conversation
share one database transaction; repeating a company save cannot create another
person, and repeating an existing-person link cannot duplicate today's capture
conversation. Dates use Europe/Berlin for the daily check.

**Decision maker** remains a separate descriptive field. Typing text there or
mentioning a name in free-form notes does not create a person.

Regression coverage lives in `tests/test_web_person_capture.py`,
`tests/integration/test_web_person_capture_db.py`, and
`tests/e2e/test_web_company_people_flow.py`. The end-to-end test fails against the
previous code, and controlled mutations check that losing the company, country,
conversation, duplicate rejection, existing-company guard, or transaction makes
the tests fail.
