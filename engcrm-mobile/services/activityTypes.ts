// What kind of work a logged activity was. Organizations and people store their own
// words for the older types ("in_person" vs "visit", "phone" vs "call"); both map onto
// the same activity types, as gcrm/activity_types.py does (_METHOD_TYPES).
// tests/test_mobile_activity_types.py fails if they drift apart. One entry per line so
// that test can read this file.

export const METHOD_TYPES: Record<string, string> = {
  in_person: "drop_in",
  visit: "drop_in",
  meeting: "meeting",
  phone: "phone",
  call: "phone",
  video: "video",
  email: "email",
  letter: "post_mail",
};

// Log entries a next-step change wrote: a plan, not work done.
const PLAN_LABELS: Record<string, string> = {
  next_step: "nextStep.title",
  next_step_done: "nextStep.doneLog",
};

/**
 * The i18n key naming a history entry's method, as the web pages name it, or null for
 * none. An organization calls anything untyped a note; a person's "other" is "Other"
 * and a person's entry with no method gets no label.
 */
export function methodLabelKey(method: string | null | undefined, owner: "organization" | "person"): string | null {
  const stored = (method ?? "").trim();
  if (PLAN_LABELS[stored]) return PLAN_LABELS[stored];
  if (METHOD_TYPES[stored]) return `activity.${METHOD_TYPES[stored]}`;
  if (owner === "person") return stored === "other" ? "personDetail.notes.methodOther" : null;
  return "activity.note";
}
