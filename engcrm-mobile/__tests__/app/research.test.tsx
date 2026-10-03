import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

const mockRun = jest.fn();
const mockOverview = jest.fn();
jest.mock("../../services/api", () => ({
  runPipelineStage: (...args: any[]) => mockRun(...args),
  fetchResearchOverview: (...args: any[]) => mockOverview(...args),
}));

jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return {
    useRouter: () => ({ push: jest.fn() }),
    useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]),
  };
});

import PipelineScreen from "../../app/(drawer)/research";

const OVERVIEW = { cities: [], totals: {} };

describe("research screen", () => {
  beforeEach(() => {
    mockRun.mockReset();
    mockOverview.mockReset().mockResolvedValue(OVERVIEW);
    jest.spyOn(Alert, "alert").mockImplementation(() => {});
  });
  afterEach(() => jest.restoreAllMocks());

  async function typeCity(text: string) {
    const screen = render(<PipelineScreen />);
    await waitFor(() => expect(mockOverview).toHaveBeenCalled());
    await act(async () => {});
    fireEvent.changeText(screen.getByPlaceholderText("e.g. München"), text);
    return screen;
  }

  it("queues straight away when the server accepts the city", async () => {
    mockRun.mockResolvedValue({ status: "queued" });
    const screen = await typeCity("Augsburg");
    fireEvent.press(screen.getByText("1 · Research"));
    await waitFor(() => expect(Alert.alert).toHaveBeenCalled());
    expect(mockRun).toHaveBeenCalledWith("research", {
      city: "Augsburg", level: 1, country: "DE", confirmed: false,
    });
    expect(screen.queryByTestId("city-confirm")).toBeNull();
  });

  it("offers the candidates, then resends the chosen one as confirmed", async () => {
    mockRun
      .mockResolvedValueOnce({
        status: "needs_confirmation", typed: "Landsberg",
        candidates: [{ name: "Landsberg am Lech", state: "Bayern", type: "town" }],
      })
      .mockResolvedValueOnce({ status: "queued" });
    const screen = await typeCity("Landsberg");
    fireEvent.press(screen.getByText("1 · Research"));
    const choice = await screen.findByText("Landsberg am Lech · Bayern");
    expect(Alert.alert).not.toHaveBeenCalled();

    fireEvent.press(choice);
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(2));
    expect(mockRun).toHaveBeenLastCalledWith("research", {
      city: "Landsberg am Lech", level: 1, country: "DE", confirmed: true,
    });
    await waitFor(() => expect(Alert.alert).toHaveBeenCalled());
    expect(screen.queryByTestId("city-confirm")).toBeNull();
    expect(screen.getByDisplayValue("Landsberg am Lech")).toBeTruthy();
  });

  it("lets an unrecognised city go through as typed", async () => {
    mockRun
      .mockResolvedValueOnce({ status: "needs_confirmation", typed: "Xyz", candidates: [] })
      .mockResolvedValueOnce({ status: "queued" });
    const screen = await typeCity("Xyz");
    fireEvent.press(screen.getByText("2 · Scout"));
    fireEvent.press(await screen.findByText("Use “Xyz” as typed"));
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(2));
    expect(mockRun).toHaveBeenLastCalledWith("scout", expect.objectContaining({ city: "Xyz", confirmed: true }));
  });

  it("cancel dismisses the choices without queueing", async () => {
    mockRun.mockResolvedValue({ status: "needs_confirmation", typed: "Xyz", candidates: [] });
    const screen = await typeCity("Xyz");
    fireEvent.press(screen.getByText("1 · Research"));
    fireEvent.press(await screen.findByText("Cancel"));
    expect(screen.queryByTestId("city-confirm")).toBeNull();
    expect(mockRun).toHaveBeenCalledTimes(1);
  });

  it("runs opportunity analysis without a city", async () => {
    mockRun.mockResolvedValue({ status: "queued" });
    const screen = render(<PipelineScreen />);
    await act(async () => {});
    fireEvent.press(screen.getByText("Run Opportunity analysis (all cities)"));
    await waitFor(() => expect(mockRun).toHaveBeenCalled());
    expect(mockRun).toHaveBeenCalledWith("opportunity", expect.objectContaining({ city: "" }));
  });
});
