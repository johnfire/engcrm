import { Alert, Linking } from "react-native";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockFetchPerson = jest.fn();
const mockDeletePerson = jest.fn();
const mockUpdateStage = jest.fn();
jest.mock("../../services/api", () => ({
  updatePersonStage: (...args: any[]) => mockUpdateStage(...args),
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
const mockPush = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "7" }),
  useRouter: () => ({ back: mockBack, replace: mockReplace, canGoBack: mockCanGoBack, push: mockPush }),
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

describe("person detail — stage", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    mockFetchPerson.mockReset();
    mockGetRole.mockReset();
    mockUpdateStage.mockReset();
    mockFetchPerson.mockResolvedValue({ ...PERSON, pipeline_stage: "candidate", company_pipeline_stage: "suspect" });
  });

  it("lets the admin change a person's stage with one tap", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockUpdateStage.mockResolvedValue({ pipeline_stage: "prospect" });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
    expect(screen.getByText("Their organization: Suspect")).toBeTruthy();
    fireEvent.press(screen.getByLabelText("Prospect"));
    await waitFor(() => expect(mockUpdateStage).toHaveBeenCalledWith(7, "prospect"));
  });

  it("does not show the stage picker to anyone but the admin", async () => {
    mockGetRole.mockResolvedValue("viewer");
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    expect(screen.queryByLabelText("Prospect")).toBeNull();
  });

  it("works for a person with no stage yet", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockFetchPerson.mockResolvedValue({ ...PERSON });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    expect(screen.getByLabelText("Prospect").props.accessibilityState.selected).toBe(false);
  });
});

describe("person detail — edit", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON });
    mockGetRole.mockReset();
    mockPush.mockReset();
  });

  it("opens the edit form for the admin", async () => {
    mockGetRole.mockResolvedValue("admin");
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Edit")).toBeTruthy());
    fireEvent.press(screen.getByText("Edit"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-person", params: { id: "7" } });
  });

  it("does not offer it to anyone else", async () => {
    mockGetRole.mockResolvedValue("viewer");
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    expect(screen.queryByText("Edit")).toBeNull();
  });
});

describe("person detail — LinkedIn", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    mockGetRole.mockReset().mockResolvedValue("spectator");
  });

  it("shows the profile and opens it with one tap", async () => {
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(true as never);
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON, linkedin_url: "https://www.linkedin.com/in/anna-roth" });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("linkedin.com/in/anna-roth ↗")).toBeTruthy());

    fireEvent.press(screen.getByLabelText("Open the LinkedIn profile of Anna Roth"));

    await waitFor(() => expect(openURL).toHaveBeenCalledWith("https://www.linkedin.com/in/anna-roth"));
  });

  it("shows nothing for a person without a profile", async () => {
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON, linkedin_url: null });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    expect(screen.queryByLabelText("Open the LinkedIn profile of Anna Roth")).toBeNull();
  });
});
