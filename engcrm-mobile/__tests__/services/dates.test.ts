import { formatDay, formatDayTime, parseDay } from "../../services/dates";

const TODAY = new Date(2026, 10, 2);

describe("dates", () => {
  it("shows a day as 28.10.2026", () => {
    expect(formatDay("2026-10-28")).toBe("28.10.2026");
    expect(formatDay("2026-01-05")).toBe("05.01.2026");
    expect(formatDay(null)).toBe("");
    expect(formatDay("next spring")).toBe("next spring");
  });

  it("shows a moment with its local time", () => {
    const local = new Date(2026, 9, 28, 14, 7).toISOString();
    expect(formatDayTime(local)).toBe("28.10.2026 14:07");
    expect(formatDay(local)).toBe("28.10.2026");
    expect(formatDayTime("2026-10-28")).toBe("28.10.2026");
  });

  it.each([
    ["28.10.2026", "2026-10-28"], [" 5.1.2026 ", "2026-01-05"], ["28/10/2026", "2026-10-28"],
    ["28.10.26", "2026-10-28"], ["28.10.", "2026-10-28"], ["2026-10-28", "2026-10-28"],
  ])("reads %s as %s", (typed, iso) => {
    expect(parseDay(typed, TODAY)).toBe(iso);
  });

  it("is null when blank and undefined for anything that is not a real day", () => {
    expect(parseDay("  ", TODAY)).toBeNull();
    for (const bad of ["10/28/2026", "31.02.2026", "28.13.2026", "yesterday", "2026-28-10"]) {
      expect(parseDay(bad, TODAY)).toBeUndefined();
    }
  });
});
