import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockCreate = jest.fn();
const mockEdit = jest.fn();
const mockFetch = jest.fn();
jest.mock("../../services/api", () => ({
  createOrganization: (...a: any[]) => mockCreate(...a),
  editOrganization: (...a: any[]) => mockEdit(...a),
  fetchOrganization: (...a: any[]) => mockFetch(...a),
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

import EditOrganizationScreen from "../../app/(drawer)/edit-organization";
import { onChanged, organizationKey } from "../../services/refreshBus";

const ORG = {
  id: 42, name: "Acme Salon", city: "Berlin", country: "DE", type: "salon", email: "a@acme.de",
  phone: null, website: "https://acme.de", notes: "old note", do_not_contact: false,
  decision_maker: null, preferred_contact_method: null,
};

describe("edit organization", () => {
  let alert: jest.SpyInstance;
  beforeEach(() => {
    jest.clearAllMocks();
    mockCanGoBack.mockReturnValue(true);
    mockGetRole.mockResolvedValue("admin");
    mockFetch.mockResolvedValue(ORG);
    mockEdit.mockResolvedValue(undefined);
    alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  });
  afterEach(() => alert.mockRestore());

  describe("editing", () => {
    beforeEach(() => {
      mockParams = { id: "42" };
    });

    it("shows the current values and saves only what changed, then refreshes the screen underneath", async () => {
      const changed = jest.fn();
      const off = onChanged(organizationKey(42), changed);
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Acme Salon")).toBeTruthy());
      expect(screen.getByDisplayValue("a@acme.de")).toBeTruthy();
      fireEvent.changeText(screen.getByLabelText("Phone"), "030 123");
      fireEvent.changeText(screen.getByLabelText("City"), "Munich");
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() => expect(mockBack).toHaveBeenCalled());
      expect(mockEdit).toHaveBeenCalledWith(42, { phone: "030 123", city: "Munich" });
      expect(changed).toHaveBeenCalledTimes(1);
      off();
    });

    it("can clear a field", async () => {
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("https://acme.de")).toBeTruthy());
      fireEvent.changeText(screen.getByLabelText("Website"), "");
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() => expect(mockEdit).toHaveBeenCalledWith(42, { website: "" }));
    });

    it("keeps the form and shows the server's message when saving fails", async () => {
      mockEdit.mockRejectedValue({ response: { data: { detail: "name is too long (max 200)" } } });
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Acme Salon")).toBeTruthy());
      fireEvent.changeText(screen.getByLabelText("Phone"), "1");
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() => expect(screen.getByText("name is too long (max 200)")).toBeTruthy());
      expect(mockBack).not.toHaveBeenCalled();
      expect(screen.getByDisplayValue("1")).toBeTruthy();
    });

    it("turning on Do not contact is saved with the form, without a question", async () => {
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByLabelText("Do not contact")).toBeTruthy());
      fireEvent(screen.getByLabelText("Do not contact"), "valueChange", true);
      expect(alert).not.toHaveBeenCalled();
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() => expect(mockEdit).toHaveBeenCalledWith(42, { do_not_contact: true }));
    });

    it("turning Do not contact off asks first, and does nothing if refused", async () => {
      mockFetch.mockResolvedValue({ ...ORG, do_not_contact: true });
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByLabelText("Do not contact").props.value).toBe(true));
      fireEvent(screen.getByLabelText("Do not contact"), "valueChange", false);
      expect(alert).toHaveBeenCalledTimes(1);
      expect(screen.getByLabelText("Do not contact").props.value).toBe(true); // not changed yet
      const buttons = alert.mock.calls[0][2] as any[];
      buttons.find((b) => b.style === "destructive").onPress();
      await waitFor(() => expect(screen.getByLabelText("Do not contact").props.value).toBe(false));
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() => expect(mockEdit).toHaveBeenCalledWith(42, { do_not_contact: false }));
    });

    it("goes to the organization when there is nothing to go back to", async () => {
      mockCanGoBack.mockReturnValue(false);
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Acme Salon")).toBeTruthy());
      fireEvent.changeText(screen.getByLabelText("Phone"), "1");
      fireEvent.press(screen.getByText("Save changes"));
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "42" } }),
      );
    });

    it("says so when the organization cannot be loaded", async () => {
      mockFetch.mockRejectedValue(new Error("offline"));
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByText("Couldn't load — check your connection")).toBeTruthy());
    });

    it("is for the admin only", async () => {
      mockGetRole.mockResolvedValue("viewer");
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByText("Only the admin can add or change records.")).toBeTruthy());
      expect(screen.queryByText("Save changes")).toBeNull();
    });
  });

  describe("adding", () => {
    beforeEach(() => {
      mockParams = { name: "Neue Firma" };
      mockCreate.mockResolvedValue({ id: 99 });
    });

    it("starts from the name typed in Search, offers no Do-not-contact switch, and opens the new organization", async () => {
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Neue Firma")).toBeTruthy());
      expect(screen.queryByLabelText("Do not contact")).toBeNull();
      fireEvent.changeText(screen.getByLabelText("City"), "Ulm");
      fireEvent.press(screen.getByText("Add organization"));
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "99" } }),
      );
      expect(mockCreate).toHaveBeenCalledWith({ name: "Neue Firma", city: "Ulm" });
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("offers to open an organization that already exists instead of adding a second", async () => {
      mockCreate.mockRejectedValue({
        response: { status: 409, data: { detail: { existing_id: 5, existing_name: "Neue Firma", existing_city: "Ulm" } } },
      });
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Neue Firma")).toBeTruthy());
      fireEvent.press(screen.getByText("Add organization"));
      await waitFor(() => expect(alert).toHaveBeenCalled());
      expect(alert.mock.calls[0][1]).toBe("Neue Firma, Ulm already exists. Open it instead?");
      (alert.mock.calls[0][2] as any[]).find((b) => b.text === "Open").onPress();
      expect(mockReplace).toHaveBeenCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "5" } });
    });

    it("explains a deleted duplicate and a blocked chain, with nothing to open", async () => {
      mockCreate.mockRejectedValueOnce({
        response: { status: 409, data: { detail: { existing_id: null, existing_name: "Neue Firma", existing_city: "Ulm" } } },
      });
      const screen = render(<EditOrganizationScreen />);
      await waitFor(() => expect(screen.getByDisplayValue("Neue Firma")).toBeTruthy());
      fireEvent.press(screen.getByText("Add organization"));
      await waitFor(() => expect(alert).toHaveBeenCalledTimes(1));
      expect(alert.mock.calls[0][1]).toMatch(/was deleted/);
      mockCreate.mockRejectedValueOnce({ response: { status: 409, data: { detail: { existing_id: null } } } });
      fireEvent.press(screen.getByText("Add organization"));
      await waitFor(() => expect(alert).toHaveBeenCalledTimes(2));
      expect(alert.mock.calls[1][1]).toMatch(/ignored-chains/);
      expect(mockReplace).not.toHaveBeenCalled();
    });
  });
});
