import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetch = jest.fn();
const mockSave = jest.fn();
const mockRole = jest.fn();
const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockNotify = jest.fn();
let mockParams = { kind: "person", id: "1" };
const record = { id: 1, kind: "person", name: "Ann", interaction_id: 9, contact_date: "2026-10-04" };
jest.mock("../../services/contact-dates", () => ({
  fetchContactDate: (...arguments_: unknown[]) => mockFetch(...arguments_),
  saveContactDate: (...arguments_: unknown[]) => mockSave(...arguments_),
}));
jest.mock("../../services/auth", () => ({ getRole: () => mockRole() }));
jest.mock("../../services/refreshBus", () => ({
  notifyChanged: (...arguments_: unknown[]) => mockNotify(...arguments_),
  organizationKey: (id: number) => `organization:${id}`, personKey: (id: number) => `person:${id}`,
}));
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ back: mockBack, replace: mockReplace, canGoBack: () => true }),
}));
import ContactDateScreen from "../../app/(drawer)/contact-date";
import { dateInDays } from "../../services/followUps";

beforeEach(() => {
  jest.clearAllMocks();
  mockParams = { kind: "person", id: "1" };
  mockRole.mockResolvedValue("admin");
  mockFetch.mockResolvedValue(record);
  mockSave.mockResolvedValue({ ...record, contact_date: "2026-10-03" });
});

it("edits the actual day and refreshes details after saving", async () => {
  const screen = render(<ContactDateScreen />);
  await waitFor(() => expect(screen.getByDisplayValue("2026-10-04")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Contact date"), "2026-10-03");
  fireEvent.press(screen.getByText("Save"));
  await waitFor(() => expect(mockSave).toHaveBeenCalledWith(record, "2026-10-03"));
  expect(mockNotify).toHaveBeenCalledWith("person:1");
  expect(mockBack).toHaveBeenCalled();
});

it("offers local yesterday and two days ago without saving before confirmation", async () => {
  const screen = render(<ContactDateScreen />);
  await waitFor(() => expect(screen.getByText("Yesterday")).toBeTruthy());
  fireEvent.press(screen.getByText("Yesterday"));
  expect(screen.getByDisplayValue(dateInDays(-1))).toBeTruthy();
  fireEvent.press(screen.getByText("Two days ago"));
  expect(screen.getByDisplayValue(dateInDays(-2))).toBeTruthy();
  expect(mockSave).not.toHaveBeenCalled();
});

it("keeps the chosen date when validation or a stale-history check fails", async () => {
  mockSave.mockRejectedValue({ response: { data: { detail: "Contact history changed. Reopen the date editor and try again." } } });
  const screen = render(<ContactDateScreen />);
  await waitFor(() => expect(screen.getByDisplayValue("2026-10-04")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Contact date"), "2026-10-03");
  fireEvent.press(screen.getByText("Save"));
  await waitFor(() => expect(screen.getByText("Contact history changed. Reopen the date editor and try again.")).toBeTruthy());
  expect(screen.getByDisplayValue("2026-10-03")).toBeTruthy();
  expect(mockBack).not.toHaveBeenCalled();
  expect(mockNotify).not.toHaveBeenCalled();
});

it("records a missing organization contact and signals the correct detail screen", async () => {
  mockParams = { kind: "organization", id: "1" };
  const missing = { ...record, kind: "organization", interaction_id: null, contact_date: null };
  mockFetch.mockResolvedValue(missing);
  const screen = render(<ContactDateScreen />);
  await waitFor(() => expect(screen.getByText("No contact recorded yet. Enter the day you actually contacted them.")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Contact date"), "2026-10-02");
  fireEvent.press(screen.getByText("Save"));
  await waitFor(() => expect(mockSave).toHaveBeenCalledWith(missing, "2026-10-02"));
  expect(mockNotify).toHaveBeenCalledWith("organization:1");
});

it("refuses viewers and malformed destinations", async () => {
  mockRole.mockResolvedValue("spectator");
  const screen = render(<ContactDateScreen />);
  await waitFor(() => expect(screen.getByText("Only the admin can add or change records.")).toBeTruthy());
  expect(mockFetch).not.toHaveBeenCalled();
  screen.unmount();
  mockParams = { kind: "unknown", id: "bad" };
  const malformed = render(<ContactDateScreen />);
  expect(malformed.getByText("Could not load the contact date. Please reopen this screen.")).toBeTruthy();
});

it("handles role and loading failures without presenting a writable form", async () => {
  mockRole.mockRejectedValueOnce(new Error("offline"));
  const forbidden = render(<ContactDateScreen />);
  await waitFor(() => expect(forbidden.getByText("Only the admin can add or change records.")).toBeTruthy());
  forbidden.unmount();
  mockFetch.mockRejectedValueOnce(new Error("offline"));
  const failed = render(<ContactDateScreen />);
  await waitFor(() => expect(failed.getByText("Could not load the contact date. Please reopen this screen.")).toBeTruthy());
  expect(failed.queryByText("Save")).toBeNull();
});
