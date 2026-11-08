import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockDeleteSale = jest.fn();
jest.mock("../../services/api", () => ({
  deleteOrganizationSale: (...a: any[]) => mockDeleteSale(...a),
}));
const mockFetchDeals = jest.fn();
const mockRecordSale = jest.fn();
const mockChangeStatus = jest.fn();
jest.mock("../../services/deals", () => ({
  fetchDeals: (...a: any[]) => mockFetchDeals(...a),
  recordSale: (...a: any[]) => mockRecordSale(...a),
  changeSaleStatus: (...a: any[]) => mockChangeStatus(...a),
}));

import { SalesCard } from "../../components/SalesCard";
import { onChanged, organizationKey } from "../../services/refreshBus";

const DEAL = (id: number, offer_name: string) => ({ id, offer_name, offer_slug: offer_name.toLowerCase() });
const SALE = { id: 5, deal_id: 8, amount_eur: "2400.00", won_on: "2026-10-28", description: "Painting", offer: "Art" };
const BOOKED = { ...SALE, id: 6, status: "booked" as const, expected_on: "2027-01-20", description: "AI course" };

beforeEach(() => {
  jest.clearAllMocks();
  mockFetchDeals.mockResolvedValue([DEAL(7, "Consulting"), DEAL(8, "Art")]);
  mockRecordSale.mockResolvedValue(undefined);
  mockDeleteSale.mockResolvedValue(undefined);
  mockChangeStatus.mockResolvedValue(undefined);
});

it("lists the sales as the web does", () => {
  const screen = render(<SalesCard organizationId={42} sales={[SALE]} canEdit={false} />);
  expect(screen.getByText("2.400 €")).toBeTruthy();
  expect(screen.getByText(/28\.10\.2026 · Art · Painting/)).toBeTruthy();
  expect(screen.queryByText("Record sale")).toBeNull(); // spectators only look
  expect(screen.queryByText("Delete")).toBeNull();
});

it("says so when there are none", () => {
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit={false} />);
  expect(screen.getByText("No sales recorded yet.")).toBeTruthy();
});

it("records a sale on the chosen deal and refreshes the organization", async () => {
  const changed = jest.fn();
  const off = onChanged(organizationKey(42), changed);
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit />);
  await waitFor(() => expect(screen.getByLabelText("Art")).toBeTruthy());
  fireEvent.press(screen.getByLabelText("Art"));
  fireEvent.changeText(screen.getByLabelText("Amount (€)"), "1200,50");
  fireEvent.changeText(screen.getByLabelText("Date won"), "27.10.2026");
  fireEvent.changeText(screen.getByLabelText("What"), " Print series ");
  fireEvent.press(screen.getByText("Record sale"));
  await waitFor(() =>
    expect(mockRecordSale).toHaveBeenCalledWith(8, "1200.50", "2026-10-27", "Print series", "booked", null),
  );
  await waitFor(() => expect(changed).toHaveBeenCalled());
  off();
});

it("refuses an amount that is not above 0, and sends nothing", async () => {
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit />);
  await waitFor(() => expect(screen.getByLabelText("Amount (€)")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Amount (€)"), "0");
  fireEvent.press(screen.getByText("Record sale"));
  await waitFor(() => expect(screen.getByText(/Enter an amount above 0/)).toBeTruthy());
  expect(mockRecordSale).not.toHaveBeenCalled();
});

it("needs a deal before a sale can be recorded", async () => {
  mockFetchDeals.mockResolvedValue([]);
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit />);
  await waitFor(() => expect(screen.getByText(/Pitch an offer to this organization first/)).toBeTruthy());
  expect(screen.queryByText("Record sale")).toBeNull();
});

it("deletes a sale after asking", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = render(<SalesCard organizationId={42} sales={[SALE]} canEdit />);
  fireEvent.press(screen.getByText("Delete"));
  const confirm = alert.mock.calls[0][2]!.find((button) => button.style === "destructive")!;
  confirm.onPress!();
  await waitFor(() => expect(mockDeleteSale).toHaveBeenCalledWith(42, 5));
  alert.mockRestore();
});

it("shows each sale's status, and a sale without one as collected", () => {
  const screen = render(<SalesCard organizationId={42} sales={[SALE, BOOKED]} canEdit={false} />);
  expect(screen.getByText("Collected")).toBeTruthy(); // an older server sends no status
  expect(screen.getByText("Booked · expected 20.01.2027")).toBeTruthy();
});

it("records a new sale as booked unless another status is picked, with the expected day", async () => {
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit />);
  await waitFor(() => expect(screen.getByLabelText("Amount (€)")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Amount (€)"), "900");
  fireEvent.press(screen.getByLabelText("Contracted"));
  fireEvent.changeText(screen.getByLabelText("Expected on (optional)"), "20.01.2027");
  fireEvent.press(screen.getByText("Record sale"));
  await waitFor(() =>
    expect(mockRecordSale).toHaveBeenCalledWith(7, "900", expect.any(String), "", "contracted", "2027-01-20"),
  );
});

it("moves a sale along and refreshes", async () => {
  const changed = jest.fn();
  const off = onChanged(organizationKey(42), changed);
  const screen = render(<SalesCard organizationId={42} sales={[BOOKED]} canEdit />);
  fireEvent.press(screen.getByLabelText("Move to Collected"));
  await waitFor(() => expect(mockChangeStatus).toHaveBeenCalledWith(8, 6, "collected"));
  await waitFor(() => expect(changed).toHaveBeenCalled());
  off();
});

it("does not offer to move a sale to the status it already has", () => {
  const screen = render(<SalesCard organizationId={42} sales={[BOOKED]} canEdit />);
  expect(screen.queryByLabelText("Move to Booked")).toBeNull();
  expect(screen.getByLabelText("Move to Cancelled")).toBeTruthy();
});

it("can record a sale as merely expected, the first step before booked", async () => {
  const screen = render(<SalesCard organizationId={42} sales={[]} canEdit />);
  await waitFor(() => expect(screen.getByLabelText("Amount (€)")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Amount (€)"), "5000");
  fireEvent.press(screen.getByLabelText("Expected"));
  fireEvent.press(screen.getByText("Record sale"));
  await waitFor(() =>
    expect(mockRecordSale).toHaveBeenCalledWith(7, "5000", expect.any(String), "", "expected", null),
  );
});

it("lists the statuses in the order a sale moves through them", () => {
  const { SALE_STATUSES } = jest.requireActual("../../services/saleStatus");
  expect(SALE_STATUSES).toEqual(["expected", "booked", "contracted", "collected", "cancelled"]);
});

it("says which payment of a contract a sale is", () => {
  const payment = { ...BOOKED, id: 7, series_id: "6f1c2f1e", series_part: 2, series_total: 4, expected_on: "2027-03-01" };
  const screen = render(<SalesCard organizationId={42} sales={[payment]} canEdit={false} />);
  expect(screen.getByText("Booked · payment 2 of 4 · expected 01.03.2027")).toBeTruthy();
});

it("shows the due day of an expected sale too, not only of booked and contracted ones", () => {
  const expected = { ...BOOKED, id: 9, status: "expected" as const, expected_on: "2027-01-31" };
  const screen = render(<SalesCard organizationId={42} sales={[expected]} canEdit={false} />);
  expect(screen.getByText("Expected · expected 31.01.2027")).toBeTruthy();
});
