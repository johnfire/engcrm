import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockCreate = jest.fn();
const mockEdit = jest.fn();
const mockFetch = jest.fn();
jest.mock("../../services/api", () => ({
  createPerson: (...a: any[]) => mockCreate(...a),
  editPerson: (...a: any[]) => mockEdit(...a),
  fetchPerson: (...a: any[]) => mockFetch(...a),
  duplicateOf: jest.requireActual("../../services/api").duplicateOf,
}));
const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: (...a: any[]) => mockGetRole(...a) }));

let mockParams: Record<string, string> = {};
const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockCanGoBack = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ back: mockBack, replace: mockReplace, canGoBack: mockCanGoBack }),
}));

import EditPersonScreen from "../../app/(drawer)/edit-person";
import { onChanged, personKey } from "../../services/refreshBus";

const PERSON = {
  id: 7, name: "Anna Roth", title: "CTO", email: null, phone: null, website: null, city: "Ulm",
  country: "DE", relationship: null, notes: null, met_at: null, company: "Acme", linkedin_url: null,
};

describe("edit person", () => {
  let alert: jest.SpyInstance;
  beforeEach(() => {
    jest.clearAllMocks();
    mockCanGoBack.mockReturnValue(true);
    mockGetRole.mockResolvedValue("admin");
    mockFetch.mockResolvedValue(PERSON);
    alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  });
  afterEach(() => alert.mockRestore());

  it("edits: shows the person and their company, saves only what changed, refreshes the person screen", async () => {
    mockParams = { id: "7" };
    mockEdit.mockResolvedValue(undefined);
    const changed = jest.fn();
    const off = onChanged(personKey(7), changed);
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Anna Roth")).toBeTruthy());
    expect(screen.getByText("Works at Acme")).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText("Position"), "CEO");
    fireEvent.press(screen.getByText("Save changes"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockEdit).toHaveBeenCalledWith(7, { title: "CEO" });
    expect(changed).toHaveBeenCalledTimes(1);
    off();
  });

  it("adds a person at an organization, starting from the name typed in Search", async () => {
    mockParams = { name: "Ben Weiss", companyId: "42", companyName: "Acme Salon" };
    mockCreate.mockResolvedValue({ id: 55 });
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Ben Weiss")).toBeTruthy());
    expect(screen.getByText("Works at Acme Salon")).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText("Email"), "ben@acme.de");
    fireEvent.press(screen.getByText("Add person"));
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "55" } }),
    );
    expect(mockCreate).toHaveBeenCalledWith({ name: "Ben Weiss", email: "ben@acme.de", contact_id: 42 });
  });

  it("adds a person with no organization", async () => {
    mockParams = { name: "Ben Weiss" };
    mockCreate.mockResolvedValue({ id: 56 });
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Ben Weiss")).toBeTruthy());
    fireEvent.press(screen.getByText("Add person"));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith({ name: "Ben Weiss" }));
  });

  it("adds a person with a starting stage; editing an existing person shows no stage picker", async () => {
    mockParams = { name: "Ben Weiss" };
    mockCreate.mockResolvedValue({ id: 57 });
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Ben Weiss")).toBeTruthy());
    fireEvent.press(screen.getByText("Prospect"));
    await waitFor(() => expect(screen.getByRole("radio", { name: "Prospect", selected: true })).toBeTruthy());
    fireEvent.press(screen.getByText("Add person"));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith({ name: "Ben Weiss", pipeline_stage: "prospect" }));

    mockParams = { id: "7" };
    const edit = render(<EditPersonScreen />);
    await waitFor(() => expect(edit.getByDisplayValue("Anna Roth")).toBeTruthy());
    expect(edit.queryByText("Prospect")).toBeNull();
  });

  it("offers to open a person who already exists", async () => {
    mockParams = { name: "Anna Roth" };
    mockCreate.mockRejectedValue({ response: { status: 409, data: { detail: { existing_id: 7 } } } });
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Anna Roth")).toBeTruthy());
    fireEvent.press(screen.getByText("Add person"));
    await waitFor(() => expect(alert).toHaveBeenCalled());
    (alert.mock.calls[0][2] as any[]).find((b) => b.text === "Open").onPress();
    expect(mockReplace).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "7" } });
  });

  it("shows the server's message when the save is refused", async () => {
    mockParams = { id: "7" };
    mockEdit.mockRejectedValue({ response: { data: { detail: "LinkedIn URL must be a linkedin.com link" } } });
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByDisplayValue("Anna Roth")).toBeTruthy());
    fireEvent.changeText(screen.getByLabelText("LinkedIn profile"), "https://example.com");
    fireEvent.press(screen.getByText("Save changes"));
    await waitFor(() => expect(screen.getByText("LinkedIn URL must be a linkedin.com link")).toBeTruthy());
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("is for the admin only", async () => {
    mockParams = { id: "7" };
    mockGetRole.mockResolvedValue("viewer");
    const screen = render(<EditPersonScreen />);
    await waitFor(() => expect(screen.getByText("Only the admin can add or change records.")).toBeTruthy());
  });
});
