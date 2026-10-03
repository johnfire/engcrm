// A tiny "this record changed" signal between screens. The meeting log saves a note,
// then the organization or person screen underneath it must reload — without the
// two screens knowing about each other or depending on navigation internals.

type Listener = () => void;
const listeners = new Map<string, Set<Listener>>();

/** Call `listener` whenever `notifyChanged(key)` is called. Returns the unsubscribe. */
export function onChanged(key: string, listener: Listener): () => void {
  let set = listeners.get(key);
  if (!set) {
    set = new Set();
    listeners.set(key, set);
  }
  set.add(listener);
  return () => {
    set?.delete(listener);
  };
}

/** Tell everything watching `key` that the record changed. One listener failing
 *  never stops the others. */
export function notifyChanged(key: string): void {
  listeners.get(key)?.forEach((listener) => {
    try {
      listener();
    } catch {
      // a screen that cannot refresh must not break the save that triggered it
    }
  });
}

export const organizationKey = (id: number) => `organization:${id}`;
export const personKey = (id: number) => `person:${id}`;
