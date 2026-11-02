// Dates for people: shown and typed European style, 28.10.2026, in every
// language. Sent to the server and stored as ISO (2026-10-28).

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const TYPED = /^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2}|\d{4})?)?$/;

const pad = (n: number) => String(n).padStart(2, "0");

/** 28.10.2026 — "" for nothing; text that is not a date is returned unchanged. */
export function formatDay(value: string | null | undefined): string {
  if (!value) return "";
  const day = ISO_DAY.exec(value.slice(0, 10));
  if (value.length <= 10 || !day) return day ? `${day[3]}.${day[2]}.${day[1]}` : value;
  const moment = new Date(value); // a timestamp: the day it is here
  return Number.isNaN(moment.getTime()) ? `${day[3]}.${day[2]}.${day[1]}`
    : `${pad(moment.getDate())}.${pad(moment.getMonth() + 1)}.${moment.getFullYear()}`;
}

/** 28.10.2026 14:07 in this phone's time zone; just the day when there is no time. */
export function formatDayTime(value: string | null | undefined): string {
  if (!value || value.length <= 10) return formatDay(value);
  const moment = new Date(value);
  if (Number.isNaN(moment.getTime())) return value;
  return `${formatDay(value)} ${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
}

/** A typed day as ISO: 28.10.2026, 28.10.26, 28/10/2026, 28.10. (this year) or
 * ISO. null when blank, undefined when it is not a real day. */
export function parseDay(text: string, today: Date = new Date()): string | null | undefined {
  const typed = text.trim();
  if (!typed) return null;
  let year: number, month: number, day: number;
  const iso = ISO_DAY.exec(typed);
  const european = TYPED.exec(typed);
  if (iso) [year, month, day] = [Number(iso[1]), Number(iso[2]), Number(iso[3])];
  else if (european) {
    const y = european[3];
    [day, month] = [Number(european[1]), Number(european[2])];
    year = y === undefined ? today.getFullYear() : Number(y) + (y.length === 2 ? 2000 : 0);
  } else return undefined;
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return undefined;
  return `${year}-${pad(month)}-${pad(day)}`;
}
