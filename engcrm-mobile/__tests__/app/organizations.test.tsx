import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetch = jest.fn();
const mockPush = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: () => Promise.resolve("admin") }));
jest.mock("../../services/api", () => ({
  ...jest.requireActual("../../services/api"),
  fetchOrganizations: (...args: unknown[]) => mockFetch(...args),
}));
jest.mock("../../services/deals", () => ({
  ...jest.requireActual("../../services/deals"),
  fetchOffers: () => Promise.resolve([
    { id: 2, slug: "learnwohl", name: "LearnWohl", website: null, revenue_kind: "subscription" },
  ]),
}));
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return {
    useRouter: () => ({ push: mockPush }),
    useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]),
  };
});
import OrganizationsScreen from "../../app/(drawer)/organizations";

const organization = {
  id: 9, name: "Galerie Nord", city: "Ulm", country: "DE", type: "gallery", pipeline_stage: "suspect",
  status: "ready", do_not_contact: false, email_bounced: false, research_exhausted: false, email: null,
  website: null, fit_score: null, flagged: false, starred: false, personal_priority: null,
  last_contact: null, created_at: "2026-07-01T00:00:00",
};

beforeEach(() => {
  jest.clearAllMocks();
  mockFetch.mockResolvedValue([organization]);
});

it("opens on the list with search and Add on screen and every filter folded away", async () => {
  const screen = render(<OrganizationsScreen />);
  await waitFor(() => expect(screen.getByText("Galerie Nord")).toBeTruthy());
  expect(screen.getByLabelText("Search city, name, type...")).toBeTruthy();
  await waitFor(() => expect(screen.getByLabelText("Add business")).toBeTruthy());
  expect(screen.queryByText("All stages")).toBeNull();
  expect(screen.queryByText("I know someone")).toBeNull();
  expect(screen.queryByText("LearnWohl")).toBeNull();
  expect(screen.getByText("Filters ▾")).toBeTruthy();
});

it("narrows the list from the panel, counts the filters and clears them", async () => {
  const screen = render(<OrganizationsScreen />);
  await waitFor(() => expect(screen.getByText("Galerie Nord")).toBeTruthy());
  fireEvent.press(screen.getByLabelText("Filters"));
  await waitFor(() => expect(screen.getByText("LearnWohl")).toBeTruthy());
  fireEvent.press(screen.getByText("LearnWohl"));
  fireEvent.press(screen.getByText("I know someone"));
  fireEvent.press(screen.getByText("Unrated"));
  fireEvent.press(screen.getByText("A–Z"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({
    offer: "learnwohl", linkedin: "1", personal_priority: "unrated", sort: "name", dir: "asc", page: 1,
  })));
  expect(screen.getByText("Filters (3) ▴")).toBeTruthy();

  fireEvent.press(screen.getByText("Clear filters"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({
    offer: "all", linkedin: "", personal_priority: "", stage: "", status: "", suppressed: "", sort: "name",
  })));
  fireEvent.press(screen.getByLabelText("Filters"));
  expect(screen.queryByText("I know someone")).toBeNull();
  expect(screen.getByText("Filters ▾")).toBeTruthy();
});
