import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockFetchHelp = jest.fn();
const mockCompleteTour = jest.fn().mockResolvedValue(undefined);
const mockFeedback = jest.fn().mockResolvedValue(undefined);
jest.mock("../../services/api", () => ({
  fetchHelp: (...args: any[]) => mockFetchHelp(...args),
  completeHelpTour: (...args: any[]) => mockCompleteTour(...args),
  sendHelpFeedback: (...args: any[]) => mockFeedback(...args),
}));

jest.mock("expo-router", () => ({
  useFocusEffect: (callback: () => void) => {
    const react = jest.requireActual<typeof import("react")>("react");
    react.useEffect(callback, []);
  },
  useLocalSearchParams: () => ({}),
}));

import HelpScreen from "../../app/(drawer)/help";

describe("Help Centre", () => {
  beforeEach(() => {
    mockFetchHelp.mockResolvedValue([{ id: 1, slug: "approvals", category: "outreach", surfaces: ["web", "mobile"], title: "Review safely", summary: "Draft first", body: "Nothing is sent automatically." }]);
    mockCompleteTour.mockClear();
    mockFeedback.mockClear();
  });

  it("opens a bilingual article and records feedback", async () => {
    const screen = render(<HelpScreen />);
    await waitFor(() => expect(screen.getByText("Review safely")).toBeTruthy());
    fireEvent.press(screen.getByText("Review safely"));
    expect(screen.getByText("Nothing is sent automatically.")).toBeTruthy();
    fireEvent.press(screen.getByText("Yes"));
    await waitFor(() => expect(mockFeedback).toHaveBeenCalledWith(1, true));
  });

  it("walks through and completes the tour", async () => {
    const screen = render(<HelpScreen />);
    await waitFor(() => expect(screen.getByText("Start the core workflow tour")).toBeTruthy());
    fireEvent.press(screen.getByText("Start the core workflow tour"));
    expect(screen.getByText("Start in Contacts to review a lead and its history.")).toBeTruthy();
    fireEvent.press(screen.getByText("Next"));
    fireEvent.press(screen.getByText("Next"));
    fireEvent.press(screen.getByText("Next"));
    fireEvent.press(screen.getByText("Finish"));
    await waitFor(() => expect(mockCompleteTour).toHaveBeenCalled());
  });
});
