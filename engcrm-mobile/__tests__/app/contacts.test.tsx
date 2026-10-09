import { FlatList } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetch = jest.fn();
const mockPush = jest.fn();
const mockRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: () => mockRole() }));
jest.mock("../../services/contact-feed", () => ({
  ...jest.requireActual("../../services/contact-feed"),
  fetchContactFeed: (...args: unknown[]) => mockFetch(...args),
  fetchContactCounts: () => Promise.reject(new Error("counts are optional")),
}));
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return {
    useRouter: () => ({ push: mockPush }),
    useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]),
  };
});
import ContactsScreen from "../../app/(drawer)/contacts";
import { ContactEntry, contactKey } from "../../services/contact-feed";

const contact = (kind: ContactEntry["kind"], id: number, name: string): ContactEntry => ({
  id, kind, name, description: "Coordinator", company: kind === "person" ? "Academy" : null,
  city: "Augsburg", email: "contact@example.test", phone: null, pipeline_stage: "candidate", created_at: "2026-10-06T10:00:00Z", last_contact: "2026-10-04",
});

beforeEach(() => {
  jest.clearAllMocks();
  mockRole.mockResolvedValue("admin");
  mockFetch.mockResolvedValue([contact("person", 1, "Ann Example"), contact("organization", 1, "Academy")]);
});

it("shows both contact types and opens their correct detail screen even with the same ID", async () => {
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByLabelText("Person: Ann Example")).toBeTruthy());
  expect(screen.getByLabelText("Organization: Academy")).toBeTruthy();
  expect(mockFetch).toHaveBeenLastCalledWith({ search: "", kind: "", stage: "", sort: "last_contact", page: 1 });
  fireEvent.press(screen.getByLabelText("Person: Ann Example"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "1" } });
  fireEvent.press(screen.getByLabelText("Organization: Academy"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "1" } });
});

it("combines search, contact type and stage and changes sort without losing filters", async () => {
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Ann Example")).toBeTruthy());
  fireEvent.changeText(screen.getByLabelText("Search people and organizations"), "Ann");
  fireEvent.press(screen.getByText("People without business"));
  fireEvent.press(screen.getAllByText("Candidate")[0]);
  fireEvent.press(screen.getByText("Name"));
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith({ search: "Ann", kind: "person", stage: "candidate", sort: "name", page: 1 }));
});

it("loads another page without dropping people who share an organization ID", async () => {
  const firstPage = [contact("person", 1, "Ann Example"), ...Array.from({ length: 49 }, (_, index) => contact("organization", index + 1, `Company ${index + 1}`))];
  mockFetch.mockImplementation(async ({ page }: { page: number }) => page === 1 ? firstPage : [contact("person", 1, "Ann Example"), contact("person", 2, "Ben Example")]);
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Ann Example")).toBeTruthy());
  const list = screen.UNSAFE_getByType(FlatList);
  await act(async () => { await list.props.onEndReached(); });
  expect(list.props.data).toHaveLength(51);
  expect(list.props.data.filter((entry: ContactEntry) => contactKey(entry) === "person-1")).toHaveLength(1);
  expect(list.props.data.some((entry: ContactEntry) => contactKey(entry) === "person-2")).toBe(true);
  expect(list.props.data.some((entry: ContactEntry) => contactKey(entry) === "organization-2")).toBe(true);
});

it("supports pull-to-refresh and reports a failed request separately from an empty list", async () => {
  mockFetch.mockRejectedValueOnce(new Error("offline"));
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Couldn't load — pull down to refresh")).toBeTruthy());
  const list = screen.UNSAFE_getByType(FlatList);
  await act(async () => { await list.props.refreshControl.props.onRefresh(); });
  expect(screen.getByText("Ann Example")).toBeTruthy();
  expect(screen.queryByText("Couldn't load — pull down to refresh")).toBeNull();
});

it("shows an empty state when neither people nor organizations match", async () => {
  mockFetch.mockResolvedValue([]);
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("No contacts found.")).toBeTruthy());
});

it("opens manual business entry for admins", async () => {
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Add business")).toBeTruthy());
  fireEvent.press(screen.getByText("Add business"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/edit-organization", params: {} });
});

it("hides business entry from viewers", async () => {
  mockRole.mockResolvedValue("viewer");
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Ann Example")).toBeTruthy());
  expect(screen.queryByText("Add business")).toBeNull();
});

it("shows the actual last contact day and opens its editor", async () => {
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getAllByText("Last contact: 2026-10-04")).toHaveLength(2));
  expect(screen.queryByText("2026-10-06")).toBeNull();
  fireEvent.press(screen.getAllByText("Last contact date")[0]);
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/contact-date", params: { kind: "person", id: "1" } });
});


it("groups linked people beneath one business and edits the person supplying the latest date", async () => {
  mockFetch.mockResolvedValue([{ ...contact("organization", 7, "Bib Academy"),
    last_contact_kind: "person", last_contact_id: 12, last_contact_name: "Anka Mufti",
    people: [{ id: 12, name: "Anka Mufti", description: "Coordinator", email: "anka@example.test",
      phone: null, city: "Augsburg", pipeline_stage: "candidate", last_contact: "2026-10-04" }],
  }]);
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("With Anka Mufti")).toBeTruthy());
  expect(screen.UNSAFE_getByType(FlatList).props.data).toHaveLength(1);
  fireEvent.press(screen.getByLabelText("Organization: Bib Academy"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "7" } });
  fireEvent.press(screen.getByText("Last contact date"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/contact-date", params: { kind: "person", id: "12" } });
  expect(screen.queryByLabelText("Person: Anka Mufti")).toBeNull();
  fireEvent.press(screen.getByText("Contacted people (1) ▾"));
  fireEvent.press(screen.getByLabelText("Person: Anka Mufti"));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "12" } });
  expect(screen.getAllByText("Last contact: 2026-10-04")).toHaveLength(2);
  fireEvent.press(screen.getByText("Contacted people (1) ▴"));
  expect(screen.queryByLabelText("Person: Anka Mufti")).toBeNull();
});

it("keeps grouped people accessible to viewers without date edit buttons", async () => {
  mockRole.mockResolvedValue("viewer");
  mockFetch.mockResolvedValue([{ ...contact("organization", 7, "Bib Academy"),
    people: [{ id: 12, name: "Anka Mufti", last_contact: "2026-10-04" }],
  }]);
  const screen = render(<ContactsScreen />);
  await waitFor(() => expect(screen.getByText("Contacted people (1) ▾")).toBeTruthy());
  fireEvent.press(screen.getByText("Contacted people (1) ▾"));
  expect(screen.getByLabelText("Person: Anka Mufti")).toBeTruthy();
  expect(screen.queryByText("Last contact date")).toBeNull();
});
