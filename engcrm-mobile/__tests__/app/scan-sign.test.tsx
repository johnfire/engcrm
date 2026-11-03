import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

const mockPush = jest.fn();
const mockCaptureSign = jest.fn();
const mockLibrary = jest.fn();
const mockCamera = jest.fn();
const mockCurrentPosition = jest.fn();
const mockLastKnown = jest.fn();

jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock("expo-image-picker", () => ({
  requestCameraPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  launchCameraAsync: (...args: unknown[]) => mockCamera(...args),
  launchImageLibraryAsync: (...args: unknown[]) => mockLibrary(...args),
}));
jest.mock("expo-image-manipulator", () => ({
  manipulateAsync: jest.fn().mockResolvedValue({ uri: "small.jpg" }),
  SaveFormat: { JPEG: "jpeg" },
}));
jest.mock("expo-location", () => ({
  Accuracy: { Balanced: 3 },
  requestForegroundPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  getCurrentPositionAsync: (...args: unknown[]) => mockCurrentPosition(...args),
  getLastKnownPositionAsync: (...args: unknown[]) => mockLastKnown(...args),
}));
jest.mock("../../services/api", () => ({
  captureSign: (...args: unknown[]) => mockCaptureSign(...args),
}));

import ScanSignScreen from "../../app/(drawer)/scan-sign";

const photo = { canceled: false, assets: [{ uri: "raw.jpg" }] };

beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  mockLibrary.mockResolvedValue(photo);
  mockCamera.mockResolvedValue(photo);
  mockCaptureSign.mockResolvedValue({ capture_id: 1, is_sign: true, fields: {}, place: null });
});

it("sends the typed town with a library photo and skips the no-location warning", async () => {
  const screen = render(<ScanSignScreen />);
  fireEvent.changeText(screen.getByLabelText("Town you're in"), "Landsberg");
  fireEvent.press(screen.getByText(/Choose from library/));

  await waitFor(() => expect(mockCaptureSign).toHaveBeenCalledWith("small.jpg", undefined, "Landsberg"));
  expect(Alert.alert).not.toHaveBeenCalled();
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/sign-confirm");
});

it("warns about a library photo with no town", async () => {
  const screen = render(<ScanSignScreen />);
  fireEvent.press(screen.getByText(/Choose from library/));

  await waitFor(() => expect(mockCaptureSign).toHaveBeenCalledWith("small.jpg", undefined, ""));
  expect(Alert.alert).toHaveBeenCalledWith("Location unavailable", expect.stringContaining("Type the town"));
});

it("keeps the town for the next photo", async () => {
  const first = render(<ScanSignScreen />);
  fireEvent.changeText(first.getByLabelText("Town you're in"), "Königsbrunn");
  first.unmount();

  const second = render(<ScanSignScreen />);
  await waitFor(() => expect(second.getByDisplayValue("Königsbrunn")).toBeTruthy());
});

it("stops waiting for a GPS fix and uses the last known position", async () => {
  jest.useFakeTimers();
  try {
    mockCurrentPosition.mockReturnValue(new Promise(() => {})); // never resolves, like a car with no fix
    mockLastKnown.mockResolvedValue({ coords: { latitude: 48.1, longitude: 10.9 } });
    const screen = render(<ScanSignScreen />);
    fireEvent.press(screen.getByText(/Take photo/));

    await act(async () => { await jest.advanceTimersByTimeAsync(10000); });

    await waitFor(() => expect(mockCaptureSign).toHaveBeenCalledWith("small.jpg", { lat: 48.1, lng: 10.9 }, ""));
  } finally {
    jest.useRealTimers();
  }
});
