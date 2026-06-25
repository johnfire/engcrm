import React from "react";
import { render } from "@testing-library/react-native";
import { ResearchCityCard } from "../../components/ResearchCityCard";
import { ResearchCity } from "../../services/api";

const LEVELS = [1, 2, 3];
const LABELS = { "1": "Handwerk", "2": "Manufacturers", "3": "Logistics" };

const city: ResearchCity = {
  id: 7,
  city: "München",
  country: "DE",
  region: "Bayern",
  levels: [
    {
      level: 1,
      scan: {
        level: 1,
        last_run_at: "2026-06-20T08:00:00Z",
        contacts_found: 12,
        run_count: 2,
        due_for_rerun: false,
        complete: true,
      },
      emailed: 5,
    },
    {
      level: 2,
      scan: {
        level: 2,
        last_run_at: "2026-06-21T08:00:00Z",
        contacts_found: 3,
        run_count: 1,
        due_for_rerun: false,
        complete: false,
      },
      emailed: 0,
    },
    { level: 3, scan: null, emailed: 0 },
  ],
  emailed_total: 5,
  total_contacts: 40,
  scanned_levels: 2,
};

describe("ResearchCityCard", () => {
  it("renders the city, region and totals", () => {
    const { getByText } = render(
      <ResearchCityCard city={city} levels={LEVELS} levelLabels={LABELS} />,
    );
    expect(getByText("München")).toBeTruthy();
    expect(getByText("Bayern")).toBeTruthy();
    // total_contacts and emailed_total surface in the footer.
    expect(getByText("40")).toBeTruthy();
  });

  it("shows a status symbol per level (complete / partial / not run)", () => {
    const { getByText } = render(
      <ResearchCityCard city={city} levels={LEVELS} levelLabels={LABELS} />,
    );
    expect(getByText("● 1")).toBeTruthy(); // complete
    expect(getByText("◐ 2")).toBeTruthy(); // partial
    expect(getByText("○ 3")).toBeTruthy(); // not run
  });

  it("renders gracefully when fields are missing/null", () => {
    const broken = {
      id: 9,
      city: null,
      country: null,
      region: null,
      levels: [],
      emailed_total: 0,
      total_contacts: 0,
      scanned_levels: 0,
    } as unknown as ResearchCity;
    const { getAllByText } = render(
      <ResearchCityCard city={broken} levels={LEVELS} levelLabels={{}} />,
    );
    // city and region both fall back to "—"; every level renders as "not run".
    expect(getAllByText("—").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText(/○ \d/).length).toBe(LEVELS.length);
  });
});
