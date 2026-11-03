import { Alert, Linking } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

jest.mock("expo-router", () => ({
  useFocusEffect: (effect: () => void) => jest.requireActual("react").useEffect(effect, [effect]),
}));

const mockIsOn = jest.fn();
const mockEndsAt = jest.fn();
const mockStart = jest.fn();
const mockStop = jest.fn();
jest.mock("../../services/fieldMode", () => ({
  FIELD_MODE_HOURS: 8,
  isFieldModeOn: (...a: any[]) => mockIsOn(...a),
  fieldModeEndsAt: (...a: any[]) => mockEndsAt(...a),
  startFieldMode: (...a: any[]) => mockStart(...a),
  stopFieldMode: (...a: any[]) => mockStop(...a),
}));

import { FieldModeCard } from "../../components/FieldModeCard";

let alert: jest.SpyInstance;
beforeEach(() => {
  jest.clearAllMocks();
  mockIsOn.mockResolvedValue(false);
  mockEndsAt.mockResolvedValue(null);
  mockStop.mockResolvedValue(undefined);
  alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
});
afterEach(() => alert.mockRestore());

function pressContinue() {
  const button = alert.mock.calls[0][2]!.find((b: any) => b.text === "Continue")!;
  button.onPress!();
}

it("explains first, then turns field mode on", async () => {
  mockStart.mockResolvedValue("started");
  const screen = render(<FieldModeCard />);
  await waitFor(() => expect(screen.getByLabelText("Field mode")).toBeTruthy());
  expect(screen.getByText(/Turns itself off after 8 hours/)).toBeTruthy();

  fireEvent(screen.getByLabelText("Field mode"), "valueChange", true);
  expect(alert.mock.calls[0][1]).toMatch(/notification the whole time/);
  expect(mockStart).not.toHaveBeenCalled(); // nothing until Continue

  mockIsOn.mockResolvedValue(true);
  mockEndsAt.mockResolvedValue(new Date(2026, 10, 3, 17, 5));
  pressContinue();
  await waitFor(() => expect(screen.getByText("On — turns itself off at 17:05")).toBeTruthy());
  expect(mockStart).toHaveBeenCalledWith({
    title: "EngCRM field mode", body: "Recording your location every 5 minutes",
  });
});

it("says what to do when location is off for the app", async () => {
  mockStart.mockResolvedValue("location-denied");
  const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
  const screen = render(<FieldModeCard />);
  await waitFor(() => expect(screen.getByLabelText("Field mode")).toBeTruthy());
  fireEvent(screen.getByLabelText("Field mode"), "valueChange", true);
  pressContinue();
  await waitFor(() => expect(screen.getByText(/Location is off for EngCRM/)).toBeTruthy());
  expect(screen.getByLabelText("Field mode").props.value).toBe(false);
  fireEvent.press(screen.getByText("Open settings"));
  expect(openSettings).toHaveBeenCalled();
  openSettings.mockRestore();
});

it("turns off at once, without asking", async () => {
  mockIsOn.mockResolvedValue(true);
  mockEndsAt.mockResolvedValue(new Date(2026, 10, 3, 17, 5));
  const screen = render(<FieldModeCard />);
  await waitFor(() => expect(screen.getByLabelText("Field mode").props.value).toBe(true));
  mockIsOn.mockResolvedValue(false);
  fireEvent(screen.getByLabelText("Field mode"), "valueChange", false);
  await waitFor(() => expect(mockStop).toHaveBeenCalled());
  expect(alert).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByText(/turns itself off at/)).toBeNull());
});
