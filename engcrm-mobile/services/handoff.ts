// One-shot, in-memory handoff between a capture screen and its confirm screen.
//
// The confirm screens (card-confirm, voice-confirm) are registered as drawer
// screens, so React Navigation mounts them once and reuses the same instance
// for every capture. Passing per-capture data through navigation params is
// fragile against that reuse (issue #18: the second capture kept showing the
// first one's data). Instead the capture screen drops the payload here and the
// confirm screen takes it on focus — guaranteed fresh, no stale mounted state.

const slots: Record<string, unknown> = {};

export function setHandoff<T>(key: string, value: T): void {
  slots[key] = value;
}

/** Return the pending payload for `key` and clear it, or null if none waiting. */
export function takeHandoff<T>(key: string): T | null {
  const value = slots[key];
  delete slots[key];
  return (value ?? null) as T | null;
}
