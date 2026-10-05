// When to follow up: the quick choices shared by "Log meeting" and a person's next
// step, and the calendar date each one means.

export const FOLLOW_UPS: { id: string; days: number | null; labelKey: string }[] = [
  { id: "none", days: null, labelKey: "meeting.followNone" },
  { id: "1d", days: 1, labelKey: "meeting.followTomorrow" },
  { id: "3d", days: 3, labelKey: "meeting.followThreeDays" },
  { id: "1w", days: 7, labelKey: "meeting.followWeek" },
  { id: "2w", days: 14, labelKey: "meeting.followTwoWeeks" },
  { id: "1m", days: 30, labelKey: "meeting.followMonth" },
];

/** The local calendar date `days` from now as YYYY-MM-DD (not UTC: after 22:00 in
 *  Bavaria "tomorrow" in UTC would be the wrong day). */
export function dateInDays(days: number, from: Date = new Date()): string {
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The follow-up choice's date, or null for "none". */
export function followUpDate(id: string, from: Date = new Date()): string | null {
  const days = FOLLOW_UPS.find((f) => f.id === id)?.days ?? null;
  return days === null ? null : dateInDays(days, from);
}
