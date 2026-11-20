// How a list is sorted, and the choice remembered between sessions.
//
// Each list offers a set of sort options, every one with the direction that suits it
// (newest first, A to Z, best status first). Tapping an option sorts that way;
// tapping the active one again reverses it. The last choice is kept on the phone.
// Storage can fail (full disk, cleared data): a list then simply opens on its default.

import AsyncStorage from "@react-native-async-storage/async-storage";

export type SortDirection = "asc" | "desc";

export interface SortOption<Key extends string = string> {
  key: Key;
  /** The direction a first tap sorts in. */
  direction: SortDirection;
  labelKey: string;
}

export interface SortChoice<Key extends string = string> {
  key: Key;
  direction: SortDirection;
}

const STORAGE_PREFIX = "list_sort_v1:";

export function defaultSort<Key extends string>(options: readonly SortOption<Key>[]): SortChoice<Key> {
  return { key: options[0].key, direction: options[0].direction };
}

/** The choice after a tap on `option`: the other way round if it was already the active sort. */
export function nextSort<Key extends string>(
  current: SortChoice<Key>,
  option: SortOption<Key>,
): SortChoice<Key> {
  if (current.key !== option.key) return { key: option.key, direction: option.direction };
  return { key: option.key, direction: current.direction === "asc" ? "desc" : "asc" };
}

/** A stored choice, or null when it is not one of `options` (an option dropped by an update). */
export function parseStoredSort<Key extends string>(
  raw: string | null,
  options: readonly SortOption<Key>[],
): SortChoice<Key> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    const known = options.some((option) => option.key === parsed?.key);
    if (!known || (parsed.direction !== "asc" && parsed.direction !== "desc")) return null;
    return { key: parsed.key, direction: parsed.direction };
  } catch {
    return null;
  }
}

export async function loadSort<Key extends string>(
  listName: string,
  options: readonly SortOption<Key>[],
): Promise<SortChoice<Key> | null> {
  try {
    return parseStoredSort(await AsyncStorage.getItem(STORAGE_PREFIX + listName), options);
  } catch {
    return null;
  }
}

export async function saveSort(listName: string, choice: SortChoice): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_PREFIX + listName, JSON.stringify(choice));
  } catch {
    // The sort still applies for this visit; it just will not be remembered.
  }
}
