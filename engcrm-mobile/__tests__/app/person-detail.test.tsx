import { Alert, Linking } from "react-native";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockFetchPerson = jest.fn();
const mockDeletePerson = jest.fn();
const mockUpdateRating = jest.fn();
jest.mock("../../services/api", () => ({
  updatePersonValueRating: (...args: any[]) => mockUpdateRating(...args),
  fetchPerson: (...args: any[]) => mockFetchPerson(...args),
  deletePerson: (...args: any[]) => mockDeletePerson(...args),
}));

// A person's stage and next step are their deals' now (the Deals panel).
const mockFetchDeals = jest.fn();
const mockChangeDeal = jest.fn();
const mockCreateDeal = jest.fn();
jest.mock("../../services/deals", () => ({
  fetchDeals: (...args: any[]) => mockFetchDeals(...args),
  fetchOffers: () => Promise.resolve([{ id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" }]),
  changeDeal: (...args: any[]) => mockChangeDeal(...args),
  createDeal: (...args: any[]) => mockCreateDeal(...args),
  removeDeal: jest.fn(),
  setDealNextStep: jest.fn(),
  startSubscription: jest.fn(),
  endSubscription: jest.fn(),
}));

const PERSON_DEAL = {
  id: 9, offer_id: 1, offer_slug: "consulting", offer_name: "Consulting", revenue_kind: "one_off",
  offer_archived: false, contact_id: null, person_id: 7, pipeline_stage: "candidate", status: "none",
  next_step: null, next_step_date: null, contact_person_id: null, contact_person_name: null,
};

beforeEach(() => {
  mockFetchDeals.mockReset().mockResolvedValue([]);
  mockChangeDeal.mockReset();
  mockCreateDeal.mockReset();
});

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

it("opens the saved-message picker from the contact screen", async () => {
  mockFetchPerson.mockResolvedValue({ ...PERSON });
  mockGetRole.mockResolvedValue("admin");
  mockPush.mockClear();
  const screen = render(<PersonDetailScreen />);
  await waitFor(() => expect(screen.getByText("Saved LinkedIn messages")).toBeTruthy());
  fireEvent.press(screen.getByText("Saved LinkedIn messages"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/saved-messages", params: { id: "7" } });
});

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
    mockFetchPerson.mockResolvedValue({ ...PERSON, pipeline_stage: "candidate", company_pipeline_stage: "suspect" });
  });

  it("lets the admin change the stage of a person's deal with one tap", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockFetchDeals.mockResolvedValue([PERSON_DEAL]);
    mockChangeDeal.mockResolvedValue({ ...PERSON_DEAL, pipeline_stage: "prospect", status: "contacted" });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
    fireEvent.press(screen.getByLabelText("Prospect"));
    await waitFor(() => expect(mockChangeDeal).toHaveBeenCalledWith(9, { stage: "prospect", status: "contacted" }));
  });

  it("does not show the stage picker to anyone but the admin", async () => {
    mockGetRole.mockResolvedValue("viewer");
    mockFetchDeals.mockResolvedValue([PERSON_DEAL]);
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Candidate · —")).toBeTruthy());
    expect(screen.queryByLabelText("Prospect")).toBeNull();
  });

  it("a person with no deal yet can be pitched an offer", async () => {
    mockGetRole.mockResolvedValue("admin");
    mockCreateDeal.mockResolvedValue({ id: 9 });
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("Nothing pitched here yet.")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("+ Consulting"));
    await waitFor(() => expect(mockCreateDeal).toHaveBeenCalledWith("person", 7, 1));
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

describe("person detail — my rating", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    mockGetRole.mockReset().mockResolvedValue("admin");
    mockUpdateRating.mockReset();
  });

  it("shows my rating and saves a new one", async () => {
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON, value_rating: 3 });
    mockUpdateRating.mockResolvedValue(1);
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("My rating")).toBeTruthy());
    expect(screen.getByLabelText("3 Medium").props.accessibilityState.selected).toBe(true);

    fireEvent.press(screen.getByLabelText("1 Exceptional"));

    await waitFor(() => expect(mockUpdateRating).toHaveBeenCalledWith(7, 1));
  });

  it("puts the old rating back and says so when saving fails", async () => {
    mockFetchPerson.mockReset().mockResolvedValue({ ...PERSON, value_rating: 3 });
    mockUpdateRating.mockRejectedValue(new Error("403"));
    const screen = render(<PersonDetailScreen />);
    await waitFor(() => expect(screen.getByText("My rating")).toBeTruthy());

    fireEvent.press(screen.getByLabelText("1 Exceptional"));

    await waitFor(() => expect(screen.getByLabelText("3 Medium").props.accessibilityState.selected).toBe(true));
  });
});
