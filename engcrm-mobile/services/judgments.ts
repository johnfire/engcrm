// How they appear to feel about me, and how they appear to me. Several of each
// may be picked per activity. The server's gcrm/activity_types.py holds the same
// lists (ATTITUDES, MY_READS) and refuses anything else.
export const ATTITUDES = ["warm", "neutral", "cold", "skeptical"] as const;
export const MY_READS = [
  "trustworthy", "straightforward", "cant_tell", "holding_back", "story_doesnt_add_up",
  "not_truthful", "indecisive", "confused", "nh", "cf",
] as const;

export type Attitude = (typeof ATTITUDES)[number];
export type MyRead = (typeof MY_READS)[number];

/** `picked` with `value` added or removed, kept in `order`'s order. */
export function toggled<T extends string>(picked: T[], value: T, order: readonly T[]): T[] {
  const next = picked.includes(value) ? picked.filter((v) => v !== value) : [...picked, value];
  return order.filter((v) => next.includes(v));
}
