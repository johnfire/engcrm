import { Alert } from "react-native";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockFetchPerson = jest.fn();
const mockDeletePerson = jest.fn();
jest.mock("../../services/api", () => ({
  fetchPerson: (...args: any[]) => mockFetchPerson(...args),
  deletePerson: (...args: any[]) => mockDeletePerson(...args),
}));

const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({
  getRole: (...args: any[]) => mockGetRole(...args),
}));

const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockCanGoBack = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "7" }),
  useRouter: () => ({ back: mockBack, replace: mockReplace, canGoBack: mockCanGoBack }),
}));

// The notes log loads and records notes on its own; this file is about the screen.
jest.mock("../../components/PersonNotesLog", () => ({ PersonNotesLog: () => null }));

import PersonDetailScreen from "../../app/(drawer)/person-detail";

const PERSON = {
  id: 7,
  name: "Anna Roth",
  title: "CTO",
  email: null,
  phone: null,
  website: null,
  city: null,
  country: null,
  relationship: null,
  notes: null,
  met_at: null,
  contact_id: null,
  company: null,
  source: "linkedin_import",
  created_at: "2026-07-01T00:00:00",
};

/** Press "Delete person" and confirm in the alert, as a user would. */
async function deleteViaAlert(screen: ReturnType<typeof render>) {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  await waitFor(() => expect(screen.getByText("Delete person")).toBeTruthy());
  fireEvent.press(screen.getByText("Delete person"));
  const buttons = alert.mock.calls[0][2]!;
  const confirm = buttons.find((button) => button.style === "destructive")!;
  await confirm.onPress!();
  return { alert, buttons };
}

describe("person detail — delete", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON });
    mockDeletePerson.mockReset();
    mockGetRole.mockReset().mockResolvedValue("admin");
    mockBack.mockReset();
    mockReplace.mockReset();
    mockCanGoBack.mockReset().mockReturnValue(true);
  });

  it("asks before deleting, then deletes and goes back", async () => {
    mockDeletePerson.mockResolvedValue(undefined);
    const screen = render(<PersonDetailScreen />);
    const { alert, buttons } = await deleteViaAlert(screen);

    expect(alert.mock.calls[0][0]).toMatch(/cannot be undone/);
    expect(buttons.some((button) => button.style === "cancel")).toBe(true);
    expect(mockDeletePerson).toHaveBeenCalledWith(7);
    expect(mockBack).toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does nothing until the alert is confirmed", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Delete person")).toBeTruthy());
    fireEvent.press(screen.getByText("Delete person"));

    expect(alert).toHaveBeenCalledTimes(1);
    expect(mockDeletePerson).not.toHaveBeenCalled();
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("goes to the people list when there is nothing to go back to", async () => {
    mockDeletePerson.mockResolvedValue(undefined);
    mockCanGoBack.mockReturnValue(false);
    await deleteViaAlert(render(<PersonDetailScreen />));

    expect(mockReplace).toHaveBeenCalledWith("/people");
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("stays on the person and says so when the delete fails", async () => {
    mockDeletePerson.mockRejectedValue(new Error("offline"));
    const screen = render(<PersonDetailScreen />);
    await deleteViaAlert(screen);

    await waitFor(() => expect(screen.getByText(/Could not delete/)).toBeTruthy());
    expect(mockBack).not.toHaveBeenCalled();
    expect(screen.getByText("Anna Roth")).toBeTruthy();
    // and the button is usable again for a retry
    expect(screen.getByText("Delete person")).toBeTruthy();
  });

  it("offers no delete to a non-admin", async () => {
    mockGetRole.mockResolvedValue("spectator");
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    expect(screen.queryByText("Delete person")).toBeNull();
  });
});
