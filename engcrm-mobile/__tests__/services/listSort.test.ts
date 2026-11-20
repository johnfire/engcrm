import AsyncStorage from "@react-native-async-storage/async-storage";

import { defaultSort, loadSort, nextSort, parseStoredSort, saveSort, SortOption } from "../../services/listSort";
import { CONTACT_SORTS, ORGANIZATION_SORTS, PERSON_SORTS } from "../../services/listSortOptions";

const options: SortOption[] = [
  { key: "newest", direction: "desc", labelKey: "a" },
  { key: "name", direction: "asc", labelKey: "b" },
];

beforeEach(async () => {
  await AsyncStorage.clear();
});

describe("nextSort", () => {
  it("starts a newly chosen sort in its own useful direction", () => {
    expect(nextSort({ key: "newest", direction: "desc" }, options[1])).toEqual({ key: "name", direction: "asc" });
  });

  it("reverses the sort that is already active, and back again", () => {
    const once = nextSort({ key: "name", direction: "asc" }, options[1]);
    expect(once).toEqual({ key: "name", direction: "desc" });
    expect(nextSort(once, options[1])).toEqual({ key: "name", direction: "asc" });
  });
});

describe("parseStoredSort", () => {
  it("reads back a saved choice", () => {
    expect(parseStoredSort('{"key":"name","direction":"desc"}', options)).toEqual({ key: "name", direction: "desc" });
  });

  it.each([
    ["nothing saved", null],
    ["not JSON", "{oops"],
    ["a sort the list no longer offers", '{"key":"gone","direction":"asc"}'],
    ["a direction that is neither", '{"key":"name","direction":"sideways"}'],
    ["JSON null", "null"],
  ])("ignores %s", (_why, raw) => {
    expect(parseStoredSort(raw, options)).toBeNull();
  });
});

describe("storage", () => {
  it("remembers a choice between sessions", async () => {
    await saveSort("people", { key: "name", direction: "desc" });
    expect(await loadSort("people", options)).toEqual({ key: "name", direction: "desc" });
  });

  it("keeps each list's choice apart", async () => {
    await saveSort("people", { key: "name", direction: "desc" });
    expect(await loadSort("organizations", options)).toBeNull();
  });

  it("never throws when storage fails", async () => {
    jest.spyOn(AsyncStorage, "getItem").mockRejectedValueOnce(new Error("disk full"));
    jest.spyOn(AsyncStorage, "setItem").mockRejectedValueOnce(new Error("disk full"));
    await expect(loadSort("people", options)).resolves.toBeNull();
    await expect(saveSort("people", { key: "name", direction: "asc" })).resolves.toBeUndefined();
  });
});

describe("the options each list offers", () => {
  it.each([
    ["organizations", ORGANIZATION_SORTS],
    ["people", PERSON_SORTS],
    ["contacts", CONTACT_SORTS],
  ])("%s: no sort is offered twice, and the default is the first", (_name, list) => {
    const keys = list.map((option) => option.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(defaultSort(list)).toEqual({ key: list[0].key, direction: list[0].direction });
  });

  it.each([
    ["organizations", ORGANIZATION_SORTS],
    ["people", PERSON_SORTS],
    ["contacts", CONTACT_SORTS],
  ])("%s: stage, status, priority-or-rating, next step and last contact can all be sorted", (_name, list) => {
    const keys = list.map((option) => option.key as string);
    for (const wanted of ["pipeline_stage", "status", "last_contact"]) expect(keys).toContain(wanted);
    expect(keys.some((key) => key.startsWith("next_"))).toBe(true);
    expect(keys.some((key) => key === "personal_priority" || key === "priority" || key === "value_rating")).toBe(true);
  });

  it("puts the best status and stage first by default", () => {
    for (const list of [ORGANIZATION_SORTS, PERSON_SORTS, CONTACT_SORTS]) {
      for (const key of ["pipeline_stage", "status"]) {
        expect(list.find((option) => option.key === key)?.direction).toBe("asc");
      }
    }
  });
});
