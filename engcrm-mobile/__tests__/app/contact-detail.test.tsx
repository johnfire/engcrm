import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockFetchContact = jest.fn();
const mockRunAnalysis = jest.fn();
const mockUpdatePersonalPriority = jest.fn();
jest.mock("../../services/api", () => ({
  fetchContact: (...args: any[]) => mockFetchContact(...args),
  runOpportunityAnalysis: (...args: any[]) => mockRunAnalysis(...args),
  updatePersonalPriority: (...args: any[]) => mockUpdatePersonalPriority(...args),
}));

const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({
  getRole: (...args: any[]) => mockGetRole(...args),
}));

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "42" }),
}));

import { Linking } from "react-native";

import ContactDetailScreen from "../../app/(drawer)/contact-detail";

const ANALYSIS = {
  opportunity_score: 82,
  confidence_score: 61,
  priority_score: 74,
  fit_reasoning: "Runs a busy salon with manual booking.",
  suggested_approach: "Offer a booking assistant demo.",
  evidence: ["Website has no online booking"],
  recommended_services: [
    { service: "Booking bot", outcome: "Fewer no-shows", rationale: "Bookings are manual today" },
  ],
  discovery_questions: ["How do clients book today?"],
  analysis_date: "2026-07-23T10:00:00",
  model_used: "cheap-llm",
};

const BASE_CONTACT = {
  id: 42,
  name: "Acme Salon",
  city: "Berlin",
  country: "DE",
  type: "salon",
  status: "cold",
  email: null,
  website: null,
  phone: null,
  notes: null,
  fit_score: null,
  flagged: false,
  starred: false,
  personal_priority: null,
  last_contact: null,
  created_at: "2026-07-01T00:00:00",
  interactions: [],
  opportunity_analysis: null,
};

describe("contact detail — opportunity analysis", () => {
  beforeEach(() => {
    mockFetchContact.mockReset();
    mockRunAnalysis.mockReset();
    mockGetRole.mockReset();
    mockUpdatePersonalPriority.mockReset();
  });

  it("lets a spectator set and clear a private priority", async () => {
    mockGetRole.mockResolvedValue("spectator");
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT });
    mockUpdatePersonalPriority
      .mockResolvedValueOnce(1)
      .mockResolvedValueOnce(null);

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("1 Best")).toBeTruthy());

    fireEvent.press(screen.getByText("1 Best"));
    await waitFor(() =>
      expect(mockUpdatePersonalPriority).toHaveBeenCalledWith(42, 1),
    );

    fireEvent.press(screen.getByText("Clear rating"));
    await waitFor(() =>
      expect(mockUpdatePersonalPriority).toHaveBeenCalledWith(42, null),
    );
  });

  it("rolls back and reports a failed priority save", async () => {
    mockGetRole.mockResolvedValue("spectator");
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, personal_priority: 2 });
    mockUpdatePersonalPriority.mockRejectedValue(new Error("offline"));

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("1 Best")).toBeTruthy());
    fireEvent.press(screen.getByText("1 Best"));

    await waitFor(() =>
      expect(
        screen.getByText("Could not save. Tap a rating to try again."),
      ).toBeTruthy(),
    );
    expect(
      screen.getByRole("radio", { name: "2 High" }).props.accessibilityState.selected,
    ).toBe(true);
  });

  it("renders a stored analysis with scores and recommended services", async () => {
    mockGetRole.mockResolvedValue("spectator");
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, opportunity_analysis: ANALYSIS });

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("Runs a busy salon with manual booking.")).toBeTruthy());
    expect(screen.getByText("82/100")).toBeTruthy();
    expect(screen.getByText("Booking bot")).toBeTruthy();
    expect(screen.getByText("How do clients book today?")).toBeTruthy();
    // A spectator never sees the run button.
    expect(screen.queryByText("Run opportunity analysis")).toBeNull();
  });

  it("lets an admin run the analysis and shows the fresh result", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT });
    mockRunAnalysis.mockResolvedValue(ANALYSIS);

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("Run opportunity analysis")).toBeTruthy());
    expect(screen.getByText("No opportunity analysis yet.")).toBeTruthy();

    fireEvent.press(screen.getByText("Run opportunity analysis"));
    await waitFor(() => expect(mockRunAnalysis).toHaveBeenCalledWith(42));
    await waitFor(() => expect(screen.getByText("Booking bot")).toBeTruthy());
    // After a successful run the button offers a re-run.
    expect(screen.getByText("Re-run analysis")).toBeTruthy();
  });

  it("surfaces an error when the analysis fails", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT });
    mockRunAnalysis.mockRejectedValue(new Error("boom"));

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("Run opportunity analysis")).toBeTruthy());
    fireEvent.press(screen.getByText("Run opportunity analysis"));
    await waitFor(() =>
      expect(screen.getByText("Analysis failed — please try again.")).toBeTruthy(),
    );
  });
});

describe("contact detail — website link", () => {
  const openURL = jest.spyOn(Linking, "openURL");

  beforeEach(() => {
    mockFetchContact.mockReset();
    mockGetRole.mockReset().mockResolvedValue("admin");
    openURL.mockReset().mockResolvedValue(true);
  });

  it("opens the stored website in the device browser, adding the missing scheme", async () => {
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, website: "acme-salon.de" });

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("acme-salon.de")).toBeTruthy());

    fireEvent.press(screen.getByText("acme-salon.de"));
    await waitFor(() => expect(openURL).toHaveBeenCalledWith("https://acme-salon.de"));
  });

  it("shows an unusable website as plain text without opening anything", async () => {
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, website: "javascript:alert(1)" });

    const screen = render(<ContactDetailScreen />);
    await waitFor(() => expect(screen.getByText("javascript:alert(1)")).toBeTruthy());

    fireEvent.press(screen.getByText("javascript:alert(1)"));
    expect(openURL).not.toHaveBeenCalled();
  });
});
