import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetchOrganizations = jest.fn();
const mockSetPersonOrganization = jest.fn();
jest.mock("../../services/api", () => ({
  fetchOrganizations: (...a: any[]) => mockFetchOrganizations(...a),
  setPersonOrganization: (...a: any[]) => mockSetPersonOrganization(...a),
}));
const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: (...a: any[]) => mockGetRole(...a) }));

let mockParams: Record<string, string> = {};
const mockBack = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ back: mockBack, replace: jest.fn(), canGoBack: () => true }),
}));

import LinkOrganizationScreen from "../../app/(drawer)/link-organization";
import { onChanged, personKey } from "../../services/refreshBus";

const ORGS = [
  { id: 42, name: "Acme GmbH", city: "Ulm" },
  { id: 43, name: "Acme Studio", city: "Augsburg" },
];

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  mockGetRole.mockResolvedValue("admin");
  mockFetchOrganizations.mockResolvedValue(ORGS);
  mockSetPersonOrganization.mockResolvedValue(undefined);
  mockParams = { id: "7", name: "Anna Roth", q: "Acme", current: "42" };
});
afterEach(() => jest.useRealTimers());

it("searches from the company it was given, and links the one tapped", async () => {
  const changed = jest.fn();
  const off = onChanged(personKey(7), changed);
  const screen = render(<LinkOrganizationScreen />);
  act(() => jest.advanceTimersByTime(300));
  await waitFor(() => expect(screen.getByText("Acme Studio")).toBeTruthy());
  expect(mockFetchOrganizations).toHaveBeenCalledWith({ search: "Acme", offer: "all" });

  // The organization they are already at cannot be linked again.
  expect(screen.getByLabelText("Link Acme GmbH").props.accessibilityState.disabled).toBe(true);
  fireEvent.press(screen.getByLabelText("Link Acme Studio"));
  await waitFor(() => expect(mockSetPersonOrganization).toHaveBeenCalledWith(7, 43));
  await waitFor(() => expect(mockBack).toHaveBeenCalled());
  expect(changed).toHaveBeenCalled();
  off();
});

it("says so when nothing matches", async () => {
  mockFetchOrganizations.mockResolvedValue([]);
  const screen = render(<LinkOrganizationScreen />);
  act(() => jest.advanceTimersByTime(300));
  await waitFor(() => expect(screen.getByText("No organizations found.")).toBeTruthy());
});

it("shows the server's message when linking fails, and stays", async () => {
  mockSetPersonOrganization.mockRejectedValue({ response: { data: { detail: "Organization not found" } } });
  const screen = render(<LinkOrganizationScreen />);
  act(() => jest.advanceTimersByTime(300));
  await waitFor(() => expect(screen.getByText("Acme Studio")).toBeTruthy());
  fireEvent.press(screen.getByLabelText("Link Acme Studio"));
  await waitFor(() => expect(screen.getByText("Organization not found")).toBeTruthy());
  expect(mockBack).not.toHaveBeenCalled();
});

it("is for the admin only", async () => {
  mockGetRole.mockResolvedValue("viewer");
  const screen = render(<LinkOrganizationScreen />);
  await waitFor(() => expect(screen.getByText(/admin/i)).toBeTruthy());
});
