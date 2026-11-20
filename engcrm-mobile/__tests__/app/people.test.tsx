import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetch = jest.fn();
const mockPush = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: () => Promise.resolve("admin") }));
jest.mock("../../services/api", () => ({
  ...jest.requireActual("../../services/api"),
  fetchPeople: (...args: unknown[]) => mockFetch(...args),
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
import PeopleScreen from "../../app/(drawer)/people";

const person = {
  id: 12, name: "Anka Mufti", title: "Coordinator", company: "Bib Academy", email: null, phone: null,
  website: null, city: "Augsburg", country: "DE", relationship: null, notes: null,
};

beforeEach(async () => {
  await AsyncStorage.clear(); // the remembered sort must not leak between tests
  jest.clearAllMocks();
  mockFetch.mockResolvedValue([person]);
});

it("opens on the list with search and Add on screen and every filter folded away", async () => {
  const screen = render(<PeopleScreen />);
  await waitFor(() => expect(screen.getByText("Anka Mufti")).toBeTruthy());
  expect(screen.getByLabelText("Search name, email, city...")).toBeTruthy();
  await waitFor(() => expect(screen.getByLabelText("Add person")).toBeTruthy());
  expect(screen.queryByText("My rating")).toBeNull();
  expect(screen.queryByText("Connections")).toBeNull();
  expect(screen.queryByText("LearnWohl")).toBeNull();
  expect(screen.getByText("Filters ▾")).toBeTruthy();
});

it("narrows the list from the panel, counts the filters and clears them", async () => {
  const screen = render(<PeopleScreen />);
  await waitFor(() => expect(screen.getByText("Anka Mufti")).toBeTruthy());
  fireEvent.press(screen.getByLabelText("Filters"));
  await waitFor(() => expect(screen.getByText("LearnWohl")).toBeTruthy());
  fireEvent.press(screen.getByText("LearnWohl"));
  fireEvent.press(screen.getByText("Connections"));
  fireEvent.press(screen.getByText("Unrated"));
  fireEvent.press(screen.getByText("A–Z"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({
    offer: "learnwohl", linkedin: "1", value_rating: "unrated", sort: "name", dir: "asc", page: 1,
  })));
  expect(screen.getByText("Filters (3) ▴")).toBeTruthy();

  fireEvent.press(screen.getByText("Clear filters"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({
    offer: "all", linkedin: "", value_rating: "", stage: "", sort: "name",
  })));
  expect(screen.queryByText("Clear filters")).toBeNull();
});

it("sorts by status best first, reverses on a second tap and remembers the choice", async () => {
  const screen = render(<PeopleScreen />);
  await waitFor(() => expect(screen.getByText("Anka Mufti")).toBeTruthy());
  expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "created_at", dir: "desc" }));
  fireEvent.press(screen.getByLabelText("Filters"));

  fireEvent.press(screen.getByText("Status"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "status", dir: "asc" })));
  fireEvent.press(screen.getByText("Status ↑"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "status", dir: "desc" })));
  expect(screen.getByText("Status ↓")).toBeTruthy();
  screen.unmount();

  // a new visit opens on the last choice, and never asks for the default order first
  mockFetch.mockClear();
  render(<PeopleScreen />);
  await waitFor(() => expect(mockFetch).toHaveBeenCalled());
  expect(mockFetch.mock.calls.every(([params]) => params.sort === "status" && params.dir === "desc")).toBe(true);
});
