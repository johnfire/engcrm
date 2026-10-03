import { FlatList } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetchOrganizations = jest.fn();
const mockFetchPeople = jest.fn();
const mockFetchReachable = jest.fn();
jest.mock("../../services/api", () => ({
  ...jest.requireActual("../../services/api"),
  fetchOrganizations: (...a: any[]) => mockFetchOrganizations(...a),
  fetchPeople: (...a: any[]) => mockFetchPeople(...a),
  fetchReachable: (...a: any[]) => mockFetchReachable(...a),
}));
const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: (...a: any[]) => mockGetRole(...a) }));

const mockPush = jest.fn();
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return {
    useRouter: () => ({ push: mockPush }),
    useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]),
  };
});

import OrganizationsScreen from "../../app/(drawer)/organizations";
import PeopleScreen from "../../app/(drawer)/people";
import ReachableScreen from "../../app/(drawer)/reachable";

const org = (id: number, name: string) => ({
  id, name, city: "Ulm", country: "DE", type: "salon", pipeline_stage: "candidate", status: "none",
  do_not_contact: false, email_bounced: false, research_exhausted: false, email: null, website: null,
  fit_score: null, flagged: false, starred: false, personal_priority: null, last_contact: null, created_at: "",
});
const person = (id: number, name: string, extra = {}) => ({
  id, name, title: "CTO", company: "Acme", city: "Ulm", email: null, is_linkedin_contact: true,
  pipeline_stage: "candidate", ...extra,
});

beforeEach(() => {
  jest.clearAllMocks();
  mockGetRole.mockResolvedValue("viewer");
});

describe("organizations list", () => {
  beforeEach(() => mockFetchOrganizations.mockResolvedValue([org(1, "Acme Salon")]));

  it("asks for the first page with the LinkedIn and flag filters empty", async () => {
    const screen = render(<OrganizationsScreen />);
    await waitFor(() => expect(screen.getByText("Acme Salon")).toBeTruthy());
    expect(mockFetchOrganizations).toHaveBeenCalledWith(expect.objectContaining({ page: 1, linkedin: "", suppressed: "" }));
  });

  it("filters to organizations where I know someone, and by a flag", async () => {
    const screen = render(<OrganizationsScreen />);
    await waitFor(() => expect(screen.getByText("Acme Salon")).toBeTruthy());
    fireEvent.press(screen.getByText("I know someone"));
    await waitFor(() =>
      expect(mockFetchOrganizations).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, linkedin: "1" })),
    );
    fireEvent.press(screen.getByText("Do not contact"));
    await waitFor(() =>
      expect(mockFetchOrganizations).toHaveBeenLastCalledWith(
        expect.objectContaining({ linkedin: "1", suppressed: "do_not_contact" }),
      ),
    );
  });

  it("asks for the next page when scrolled to the end — a full page means there may be more", async () => {
    mockFetchOrganizations.mockImplementation(async ({ page }: any) =>
      page === 1 ? Array.from({ length: 50 }, (_, i) => org(i + 1, `Org ${i + 1}`)) : [org(51, "Org 51")],
    );
    const screen = render(<OrganizationsScreen />);
    await waitFor(() => expect(screen.getByText("Org 1")).toBeTruthy());
    fireEvent(screen.UNSAFE_getByType(FlatList), "endReached");
    await waitFor(() => expect(mockFetchOrganizations).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });

  it("shows an add button to the admin only, opening the empty form", async () => {
    const viewer = render(<OrganizationsScreen />);
    await waitFor(() => expect(viewer.getByText("Acme Salon")).toBeTruthy());
    expect(viewer.queryByLabelText("Add organization")).toBeNull();
    viewer.unmount();
    mockGetRole.mockResolvedValue("admin");
    const admin = render(<OrganizationsScreen />);
    await waitFor(() => expect(admin.getByLabelText("Add organization")).toBeTruthy());
    fireEvent.press(admin.getByLabelText("Add organization"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-organization", params: {} });
  });

  it("says when it cannot load", async () => {
    mockFetchOrganizations.mockRejectedValue(new Error("offline"));
    const screen = render(<OrganizationsScreen />);
    await waitFor(() => expect(screen.getByText("Couldn't load — pull down to refresh")).toBeTruthy());
  });
});

describe("people list", () => {
  beforeEach(() => mockFetchPeople.mockResolvedValue([person(7, "Anna Roth"), person(8, "Ben Weiss", { pipeline_stage: null, is_linkedin_contact: false })]));

  it("shows each person's stage and LinkedIn badge", async () => {
    const screen = render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    expect(screen.getAllByText("in")).toHaveLength(1);
    expect(screen.getAllByText("Candidate").length).toBeGreaterThan(0);
    expect(mockFetchPeople).toHaveBeenCalledWith(expect.objectContaining({ page: 1, stage: "", linkedin: "" }));
  });

  it("filters by stage, including people with no stage, and by LinkedIn", async () => {
    const screen = render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    fireEvent.press(screen.getByText("No stage"));
    await waitFor(() => expect(mockFetchPeople).toHaveBeenLastCalledWith(expect.objectContaining({ stage: "none" })));
    fireEvent.press(screen.getByText("Not linked to an organization"));
    await waitFor(() =>
      expect(mockFetchPeople).toHaveBeenLastCalledWith(expect.objectContaining({ stage: "none", linkedin: "unlinked" })),
    );
  });

  it("sorts by when they connected, newest first", async () => {
    const screen = render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    fireEvent.press(screen.getByText("Recently connected"));
    await waitFor(() =>
      expect(mockFetchPeople).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "connected_on", dir: "desc" })),
    );
  });

  it("opens a person, and offers the admin an add button", async () => {
    mockGetRole.mockResolvedValue("admin");
    const screen = render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText("Anna Roth")).toBeTruthy());
    fireEvent.press(screen.getByText("Anna Roth"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "7" } });
    await waitFor(() => expect(screen.getByLabelText("Add person")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Add person"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-person", params: {} });
  });
});

describe("reachable fits", () => {
  const ROW = {
    id: 4, name: "Acme GmbH", city: "Ulm", country: "DE", type: "software", website: null, fit_score: 88,
    people: [
      { id: 9, name: "Anna Roth", title: "CTO", linkedin_url: null, connected_on: "2026-06-01" },
      { id: 10, name: "Ben Weiss", title: null, linkedin_url: null, connected_on: null },
    ],
  };

  it("lists each organization with the people I know there", async () => {
    mockFetchReachable.mockResolvedValue({ total: 1, rows: [ROW] });
    const screen = render(<ReachableScreen />);
    await waitFor(() => expect(screen.getByText("Acme GmbH")).toBeTruthy());
    expect(screen.getByText("88")).toBeTruthy();
    expect(screen.getByText("Anna Roth")).toBeTruthy();
    expect(screen.getByText("CTO")).toBeTruthy();
    expect(screen.getByText("Ben Weiss")).toBeTruthy();
    expect(mockFetchReachable).toHaveBeenCalledWith(1);
  });

  it("opens the organization, or the person", async () => {
    mockFetchReachable.mockResolvedValue({ total: 1, rows: [ROW] });
    const screen = render(<ReachableScreen />);
    await waitFor(() => expect(screen.getByText("Acme GmbH")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Acme GmbH"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "4" } });
    fireEvent.press(screen.getByLabelText("Anna Roth"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "9" } });
  });

  it("explains an empty list, and a failed load", async () => {
    mockFetchReachable.mockResolvedValue({ total: 0, rows: [] });
    const empty = render(<ReachableScreen />);
    await waitFor(() => expect(empty.getByText(/Nothing here yet/)).toBeTruthy());
    empty.unmount();
    mockFetchReachable.mockRejectedValue(new Error("offline"));
    const failed = render(<ReachableScreen />);
    await waitFor(() => expect(failed.getByText("Couldn't load — pull down to refresh")).toBeTruthy());
  });
});
