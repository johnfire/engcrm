import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetchDeals = jest.fn();
const mockChangeDeal = jest.fn();
const mockStart = jest.fn();
const mockEnd = jest.fn();
const mockRemove = jest.fn();
jest.mock("../../services/deals", () => ({
  ...jest.requireActual("../../services/deals"),
  fetchOffers: () => Promise.resolve([
    { id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" },
    { id: 2, slug: "learnwohl", name: "LearnWohl", website: null, revenue_kind: "subscription" },
  ]),
  fetchDeals: (...a: any[]) => mockFetchDeals(...a),
  changeDeal: (...a: any[]) => mockChangeDeal(...a),
  startSubscription: (...a: any[]) => mockStart(...a),
  endSubscription: (...a: any[]) => mockEnd(...a),
  removeDeal: (...a: any[]) => mockRemove(...a),
  createDeal: jest.fn(),
  setDealNextStep: jest.fn(),
}));

import { DealsPanel } from "../../components/DealsPanel";
import { dateInDays } from "../../services/followUps";

const LEARNWOHL = {
  id: 9, offer_id: 2, offer_slug: "learnwohl", offer_name: "LearnWohl", revenue_kind: "subscription",
  offer_archived: false, contact_id: 4, person_id: null, pipeline_stage: "customer", status: "none",
  next_step: null, next_step_date: null, contact_person_id: null, contact_person_name: null,
  money: {
    sales_total: "0", sales: [], subscriptions: [],
    running: { id: 3, amount_eur_month: "49.00", started_on: "2026-09-01", ended_on: null, note: null },
  },
};

function setup(canEdit = true) {
  return render(
    <DealsPanel owner="organization" ownerId={4} canEdit={canEdit} contactPeople={[{ id: 7, name: "Jamie Simmons" }]} />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockFetchDeals.mockResolvedValue([LEARNWOHL]);
  mockChangeDeal.mockResolvedValue(LEARNWOHL);
  mockStart.mockResolvedValue(undefined);
  mockEnd.mockResolvedValue(undefined);
});

it("shows what the deal earns, and offers only what is not pitched yet", async () => {
  const screen = setup();
  await waitFor(() => expect(screen.getByText("49.00 € / month since 2026-09-01")).toBeTruthy());
  expect(screen.getByLabelText("+ Consulting")).toBeTruthy();
  expect(screen.queryByLabelText("+ LearnWohl")).toBeNull();
});

it("names the contact person with one tap", async () => {
  const screen = setup();
  fireEvent.press(await screen.findByLabelText("Jamie Simmons"));
  await waitFor(() => expect(mockChangeDeal).toHaveBeenCalledWith(9, { contact_person_id: 7 }));
});

it("changes the price from today, and ends the subscription today", async () => {
  const screen = setup();
  fireEvent.changeText(await screen.findByLabelText("€ per month"), "59,50");
  fireEvent.press(screen.getByText("New price from today"));
  await waitFor(() => expect(mockStart).toHaveBeenCalledWith(9, "59.50", dateInDays(0)));
  fireEvent.press(await screen.findByText("End subscription today"));
  await waitFor(() => expect(mockEnd).toHaveBeenCalledWith(9, dateInDays(0)));
});

it("asks before it stops pitching an offer", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = setup();
  fireEvent.press(await screen.findByText("Stop pitching"));
  expect(alert.mock.calls[0][1]).toBe("Stop pitching LearnWohl here? Its history stays.");
  expect(mockRemove).not.toHaveBeenCalled();
  alert.mockRestore();
});

it("is read-only for everyone but the admin", async () => {
  const screen = setup(false);
  await waitFor(() => expect(screen.getByText("Customer · —")).toBeTruthy());
  expect(screen.queryByLabelText("€ per month")).toBeNull();
  expect(screen.queryByText("Stop pitching")).toBeNull();
  expect(screen.queryByLabelText("+ Consulting")).toBeNull();
});

it("says so when the deals cannot be loaded", async () => {
  mockFetchDeals.mockRejectedValue(new Error("offline"));
  const screen = setup();
  await waitFor(() => expect(screen.getByText("Couldn't load the offers pitched here.")).toBeTruthy());
});
