import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

const mockSearchAll = jest.fn();
jest.mock("../../services/api", () => ({
  searchAll: (...args: any[]) => mockSearchAll(...args),
}));

const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: (...args: any[]) => mockGetRole(...args) }));

const mockPush = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

import SearchScreen from "../../app/(drawer)/search";

const ORG = {
  id: 5, name: "IHK Schwaben", city: "Augsburg", country: "DE", type: "chamber",
  pipeline_stage: "candidate", status: "none", linkedin_connection_count: 4,
};
const PERSON = {
  id: 9, name: "Tatjana Lidl", title: "Event-Managerin", city: null, company: "IHK Schwaben",
  contact_id: 5, is_linkedin_contact: true, pipeline_stage: "candidate", company_pipeline_stage: "candidate",
};

async function typeAndWait(screen: ReturnType<typeof render>, text: string) {
  fireEvent.changeText(screen.getByLabelText("Name, company or city"), text);
  await act(async () => {
    jest.advanceTimersByTime(350);
  });
}

describe("search screen", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockSearchAll.mockReset();
    mockPush.mockReset();
    mockGetRole.mockReset().mockResolvedValue("viewer");
  });
  afterEach(() => jest.useRealTimers());

  it("starts with a hint and searches nothing", () => {
    const screen = render(<SearchScreen />);
    expect(screen.getByText(/at least two letters/)).toBeTruthy();
    expect(mockSearchAll).not.toHaveBeenCalled();
  });

  it("does not search for a single letter", async () => {
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "i");
    expect(mockSearchAll).not.toHaveBeenCalled();
  });

  it("waits for a pause in typing, then searches once", async () => {
    mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [PERSON] });
    const screen = render(<SearchScreen />);
    fireEvent.changeText(screen.getByLabelText("Name, company or city"), "ih");
    await act(async () => { jest.advanceTimersByTime(100); });
    fireEvent.changeText(screen.getByLabelText("Name, company or city"), "ihk");
    await act(async () => { jest.advanceTimersByTime(350); });
    await waitFor(() => expect(mockSearchAll).toHaveBeenCalledTimes(1));
    expect(mockSearchAll).toHaveBeenCalledWith("ihk");
  });

  it("shows organizations and people, with how many LinkedIn contacts you have there", async () => {
    mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [PERSON] });
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "ihk");
    await waitFor(() => expect(screen.getByText("IHK Schwaben")).toBeTruthy());
    expect(screen.getByText("Organizations")).toBeTruthy();
    expect(screen.getByText("People")).toBeTruthy();
    expect(screen.getByText("in 4")).toBeTruthy();         // I know 4 people at this company
    expect(screen.getByText("Augsburg, DE · chamber")).toBeTruthy();
    expect(screen.getByText("Tatjana Lidl")).toBeTruthy();
    expect(screen.getByText("Event-Managerin · IHK Schwaben")).toBeTruthy();
    expect(screen.getAllByText("Candidate").length).toBe(2);
  });

  it("opens an organization or a person when tapped", async () => {
    mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [PERSON] });
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "ihk");
    await waitFor(() => expect(screen.getByText("Tatjana Lidl")).toBeTruthy());
    fireEvent.press(screen.getByText("Tatjana Lidl"));
    expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { id: "9" } });
    fireEvent.press(screen.getByText("IHK Schwaben"));
    expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "5" } });
  });

  it("says so when nothing matches", async () => {
    mockSearchAll.mockResolvedValue({ query: "zzzz", organizations: [], people: [] });
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "zzzz");
    await waitFor(() => expect(screen.getByText("Nothing found for “zzzz”.")).toBeTruthy());
  });

  it("says so when the search fails, and recovers on the next try", async () => {
    mockSearchAll.mockRejectedValueOnce(new Error("offline"));
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "ihk");
    await waitFor(() => expect(screen.getByText(/Couldn't search/)).toBeTruthy());
    mockSearchAll.mockResolvedValue({ query: "ihkx", organizations: [ORG], people: [] });
    await typeAndWait(screen, "ihkx");
    await waitFor(() => expect(screen.getByText("IHK Schwaben")).toBeTruthy());
    expect(screen.queryByText(/Couldn't search/)).toBeNull();
  });

  it("ignores a slow old answer that arrives after a newer one", async () => {
    let answerOld: (value: unknown) => void = () => {};
    mockSearchAll
      .mockImplementationOnce(() => new Promise((resolve) => { answerOld = resolve; }))
      .mockResolvedValueOnce({ query: "ihk s", organizations: [{ ...ORG, name: "Newer Result" }], people: [] });
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "ihk");
    await typeAndWait(screen, "ihk s");
    await waitFor(() => expect(screen.getByText("Newer Result")).toBeTruthy());
    await act(async () => {
      answerOld({ query: "ihk", organizations: [{ ...ORG, name: "Stale Result" }], people: [] });
    });
    expect(screen.queryByText("Stale Result")).toBeNull();
    expect(screen.getByText("Newer Result")).toBeTruthy();
  });

  it("goes back to the hint when the box is cleared", async () => {
    mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [] });
    const screen = render(<SearchScreen />);
    await typeAndWait(screen, "ihk");
    await waitFor(() => expect(screen.getByText("IHK Schwaben")).toBeTruthy());
    await typeAndWait(screen, "");
    expect(screen.queryByText("IHK Schwaben")).toBeNull();
    expect(screen.getByText(/at least two letters/)).toBeTruthy();
  });

  describe("adding what was not found (admin)", () => {
    it("offers to add the typed name as an organization or as a person, carrying the name over", async () => {
      mockGetRole.mockResolvedValue("admin");
      mockSearchAll.mockResolvedValue({ query: "neue firma", organizations: [], people: [] });
      const screen = render(<SearchScreen />);
      await typeAndWait(screen, "Neue Firma");
      await waitFor(() => expect(screen.getByText("Add as organization")).toBeTruthy());
      expect(screen.getByText("Not found? Add “Neue Firma”:")).toBeTruthy();
      fireEvent.press(screen.getByText("Add as organization"));
      expect(mockPush).toHaveBeenCalledWith({
        pathname: "/(drawer)/edit-organization", params: { name: "Neue Firma" },
      });
      fireEvent.press(screen.getByText("Add as person"));
      expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-person", params: { name: "Neue Firma" } });
    });

    it("offers it even when there are results, since the match may be someone else", async () => {
      mockGetRole.mockResolvedValue("admin");
      mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [] });
      const screen = render(<SearchScreen />);
      await typeAndWait(screen, "ihk");
      await waitFor(() => expect(screen.getByText("IHK Schwaben")).toBeTruthy());
      expect(screen.getByText("Add as person")).toBeTruthy();
    });

    it("does not show it to anyone else, nor before there is a query", async () => {
      mockSearchAll.mockResolvedValue({ query: "ihk", organizations: [ORG], people: [] });
      const screen = render(<SearchScreen />);
      await typeAndWait(screen, "ihk");
      await waitFor(() => expect(screen.getByText("IHK Schwaben")).toBeTruthy());
      expect(screen.queryByText("Add as organization")).toBeNull();
    });

    it("shows no add rows for an empty box, even for the admin", async () => {
      mockGetRole.mockResolvedValue("admin");
      const screen = render(<SearchScreen />);
      await act(async () => { jest.advanceTimersByTime(10); });
      expect(screen.queryByText("Add as organization")).toBeNull();
    });
  });
});
