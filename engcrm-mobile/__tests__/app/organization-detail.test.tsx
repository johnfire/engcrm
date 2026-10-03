import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockFetchContact = jest.fn();
const mockRunAnalysis = jest.fn();
const mockUpdatePersonalPriority = jest.fn();
const mockUpdateState = jest.fn();
jest.mock("../../services/api", () => ({
  updateOrganizationState: (...args: any[]) => mockUpdateState(...args),
  fetchOrganization: (...args: any[]) => mockFetchContact(...args),
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

import OrganizationDetailScreen from "../../app/(drawer)/organization-detail";

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
  pipeline_stage: "suspect",
  status: "ready",
  do_not_contact: false,
  email_bounced: false,
  research_exhausted: false,
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

describe("organization detail — opportunity analysis", () => {
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

    const screen = render(<OrganizationDetailScreen />);
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

    const screen = render(<OrganizationDetailScreen />);
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

    const screen = render(<OrganizationDetailScreen />);
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

    const screen = render(<OrganizationDetailScreen />);
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

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("Run opportunity analysis")).toBeTruthy());
    fireEvent.press(screen.getByText("Run opportunity analysis"));
    await waitFor(() =>
      expect(screen.getByText("Analysis failed — please try again.")).toBeTruthy(),
    );
  });
});

describe("organization detail — website link", () => {
  const openURL = jest.spyOn(Linking, "openURL");

  beforeEach(() => {
    mockFetchContact.mockReset();
    mockGetRole.mockReset().mockResolvedValue("admin");
    openURL.mockReset().mockResolvedValue(true);
  });

  it("opens the stored website in the device browser, adding the missing scheme", async () => {
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, website: "acme-salon.de" });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("acme-salon.de")).toBeTruthy());

    fireEvent.press(screen.getByText("acme-salon.de"));
    await waitFor(() => expect(openURL).toHaveBeenCalledWith("https://acme-salon.de"));
  });

  it("shows an unusable website as plain text without opening anything", async () => {
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, website: "javascript:alert(1)" });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("javascript:alert(1)")).toBeTruthy());

    fireEvent.press(screen.getByText("javascript:alert(1)"));
    expect(openURL).not.toHaveBeenCalled();
  });
});

describe("organization detail — state", () => {
  beforeEach(() => {
    mockFetchContact.mockReset();
    // These check the read-only badges. The admin also gets a picker whose chips
    // repeat the same words; that is covered in "stage and status" below.
    mockGetRole.mockReset().mockResolvedValue("viewer");
  });

  it("shows the pipeline stage and the current status as separate facts", async () => {
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("Suspect")).toBeTruthy());
    expect(screen.getByText("Ready to contact")).toBeTruthy();
  });

  it("shows suppression flags without disturbing stage or status", async () => {
    mockFetchContact.mockResolvedValue({
      ...BASE_CONTACT,
      pipeline_stage: "opportunity",
      status: "meeting",
      do_not_contact: true,
      email_bounced: true,
    });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("Meeting")).toBeTruthy());
    // The whole point of the split: a bounce does not cost you the meeting.
    expect(screen.getByText("Opportunity")).toBeTruthy();
    expect(screen.getByText("Do not contact")).toBeTruthy();
    expect(screen.getByText("Email bounced")).toBeTruthy();
    expect(screen.queryByText("No more data findable")).toBeNull();
  });
});

describe("organization detail — LinkedIn notice", () => {
  beforeEach(() => {
    mockFetchContact.mockReset();
    mockGetRole.mockReset();
    mockGetRole.mockResolvedValue("spectator");
  });

  const ANNA = {
    id: 3,
    name: "Anna Roth",
    title: "CTO",
    linkedin_url: "https://www.linkedin.com/in/anna-roth",
    connected_on: "2024-03-05",
  };
  const BOB = {
    id: 4,
    name: "Bob Ng",
    title: null,
    linkedin_url: null,
    connected_on: null,
    company_raw: "Acme Ltd",
  };

  it("tells you who you know here, confirmed people first", async () => {
    mockFetchContact.mockResolvedValue({
      ...BASE_CONTACT,
      linkedin_connections: { linked: [ANNA], possible: [] },
    });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("You know someone here on LinkedIn")).toBeTruthy());
    expect(screen.getByText("Anna Roth · CTO")).toBeTruthy();
    expect(screen.queryByText(/Possible LinkedIn connections/)).toBeNull();
  });

  it("opens the profile of a confirmed connection", async () => {
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(true as never);
    mockFetchContact.mockResolvedValue({
      ...BASE_CONTACT,
      linkedin_connections: { linked: [ANNA], possible: [] },
    });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth · CTO")).toBeTruthy());
    fireEvent.press(screen.getByText("Anna Roth · CTO"));

    await waitFor(() => expect(openURL).toHaveBeenCalledWith("https://www.linkedin.com/in/anna-roth"));
    openURL.mockRestore();
  });

  it("labels unconfirmed lookalikes as such and shows their LinkedIn company", async () => {
    mockFetchContact.mockResolvedValue({
      ...BASE_CONTACT,
      linkedin_connections: { linked: [], possible: [BOB] },
    });

    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() =>
      expect(screen.getByText(/Possible LinkedIn connections.*unconfirmed/)).toBeTruthy(),
    );
    expect(screen.getByText("Bob Ng")).toBeTruthy();
    expect(screen.getByText("Company on LinkedIn: Acme Ltd")).toBeTruthy();
    expect(screen.queryByText("You know someone here on LinkedIn")).toBeNull();
  });

  it("shows no notice when there are no connections, or the server predates the feature", async () => {
    mockFetchContact.mockResolvedValue({
      ...BASE_CONTACT,
      linkedin_connections: { linked: [], possible: [] },
    });
    const empty = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(empty.getByText("Acme Salon")).toBeTruthy());
    expect(empty.queryByText(/LinkedIn/)).toBeNull();
    empty.unmount();

    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT });
    const legacy = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(legacy.getByText("Acme Salon")).toBeTruthy());
    expect(legacy.queryByText(/LinkedIn/)).toBeNull();
  });
});

describe("organization detail — stage and status", () => {
  beforeEach(() => {
    mockFetchContact.mockReset();
    mockGetRole.mockReset();
    mockUpdateState.mockReset();
    mockFetchContact.mockResolvedValue({ ...BASE_CONTACT, pipeline_stage: "candidate", status: "none" });
  });

  it("lets the admin move the organization along the pipeline, and the badges follow", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockUpdateState.mockResolvedValue({ pipeline_stage: "suspect", status: "ready", typical: true });
    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByLabelText("Suspect")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() =>
      expect(mockUpdateState).toHaveBeenCalledWith(42, { pipeline_stage: "suspect", status: "ready" }),
    );
    // the read-only badges above the picker now show the server's answer
    await waitFor(() => expect(screen.getAllByText("Ready to contact").length).toBeGreaterThan(0));
  });

  it("shows the picker to the admin only; everyone else just sees the badges", async () => {
    mockGetRole.mockResolvedValue("viewer");
    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByText("Acme Salon")).toBeTruthy());
    expect(screen.queryByLabelText("Suspect")).toBeNull();
    expect(screen.queryByText("Pipeline")).toBeNull();
    expect(screen.getByText("Candidate")).toBeTruthy();
  });

  it("a failed save leaves the organization where it was", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockUpdateState.mockRejectedValue(new Error("offline"));
    const screen = render(<OrganizationDetailScreen />);
    await waitFor(() => expect(screen.getByLabelText("Suspect")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(screen.getByText(/Couldn't save/)).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
  });
});

