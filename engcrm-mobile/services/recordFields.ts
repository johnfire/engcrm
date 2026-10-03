// The fields of an organization and of a person as the phone edits them, with the
// longest value each may hold. The limits are the server's (the database columns);
// tests/test_mobile_record_fields.py fails if they drift apart. One field per line
// so that test can read this file.

import type { FieldDef } from "../components/RecordForm";

export const ORGANIZATION_FIELDS: FieldDef[] = [
  { key: "name", labelKey: "recordForm.name", maxLength: 200, required: true },
  { key: "type", labelKey: "recordForm.orgType", maxLength: 60 },
  { key: "city", labelKey: "recordForm.city", maxLength: 100 },
  { key: "country", labelKey: "recordForm.country", maxLength: 2, capitals: true },
  { key: "email", labelKey: "recordForm.email", maxLength: 200, keyboard: "email-address" },
  { key: "phone", labelKey: "recordForm.phone", maxLength: 60, keyboard: "phone-pad" },
  { key: "website", labelKey: "recordForm.website", maxLength: 300, keyboard: "url" },
  { key: "decision_maker", labelKey: "recordForm.decisionMaker", maxLength: 200 },
  { key: "preferred_contact_method", labelKey: "recordForm.preferredContact", maxLength: 60 },
  { key: "notes", labelKey: "recordForm.notes", maxLength: 20000, multiline: true },
];

export const PERSON_FIELDS: FieldDef[] = [
  { key: "name", labelKey: "recordForm.name", maxLength: 200, required: true },
  { key: "title", labelKey: "recordForm.title", maxLength: 200 },
  { key: "email", labelKey: "recordForm.email", maxLength: 200, keyboard: "email-address" },
  { key: "phone", labelKey: "recordForm.phone", maxLength: 60, keyboard: "phone-pad" },
  { key: "website", labelKey: "recordForm.website", maxLength: 300, keyboard: "url" },
  { key: "linkedin_url", labelKey: "recordForm.linkedin", maxLength: 300, keyboard: "url" },
  { key: "city", labelKey: "recordForm.city", maxLength: 100 },
  { key: "country", labelKey: "recordForm.country", maxLength: 2, capitals: true },
  { key: "relationship", labelKey: "recordForm.relationship", maxLength: 100 },
  { key: "met_at", labelKey: "recordForm.metAt", maxLength: 200 },
  { key: "notes", labelKey: "recordForm.notes", maxLength: 20000, multiline: true },
];
