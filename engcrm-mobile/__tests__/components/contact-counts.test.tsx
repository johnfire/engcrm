import { render, waitFor } from "@testing-library/react-native";

const mockFetchCounts = jest.fn();
jest.mock("../../services/contact-feed", () => ({
  fetchContactCounts: () => mockFetchCounts(),
}));
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return { useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]) };
});

import { ContactCountsStrip } from "../../components/contact-counts";

const COUNTS = {
  month: { people: 3, organizations: 1 },
  since_start: { people: 12, organizations: 9 },
  business_start: "2026-10-01",
};

beforeEach(() => jest.clearAllMocks());

it("shows people and organizations for this month and since the business began", async () => {
  mockFetchCounts.mockResolvedValue(COUNTS);
  const { findByText, getByText } = render(<ContactCountsStrip />);
  expect(await findByText("3 people · 1 organization")).toBeTruthy();
  expect(getByText("12 people · 9 organizations")).toBeTruthy();
  expect(getByText("This month")).toBeTruthy();
  expect(getByText("All time (since 2026-10-01)")).toBeTruthy();
});

it("renders nothing when the counts cannot be loaded", async () => {
  mockFetchCounts.mockRejectedValue(new Error("offline"));
  const { queryByText } = render(<ContactCountsStrip />);
  await waitFor(() => expect(mockFetchCounts).toHaveBeenCalled());
  expect(queryByText("This month")).toBeNull();
});
