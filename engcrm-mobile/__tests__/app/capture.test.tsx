import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

const mockPush = jest.fn();
const mockPhoto = jest.fn();
const mockPrepare = jest.fn();
const mockCapture = jest.fn();
const mockEnqueue = jest.fn();
const mockHandoff = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  useFocusEffect: () => {},
}));
jest.mock("../../services/documentPhoto", () => ({
  chooseDocumentPhoto: (...args: unknown[]) => mockPhoto(...args),
  prepareDocumentPhoto: (...args: unknown[]) => mockPrepare(...args),
}));
jest.mock("../../services/api", () => ({ captureCard: (...args: unknown[]) => mockCapture(...args) }));
jest.mock("../../services/handoff", () => ({ setHandoff: (...args: unknown[]) => mockHandoff(...args) }));
jest.mock("../../services/cardQueue", () => ({
  enqueue: (...args: unknown[]) => mockEnqueue(...args),
  flush: jest.fn().mockResolvedValue({ remaining: 0 }),
  pendingCount: jest.fn().mockResolvedValue(0),
}));
import CaptureScreen from "../../app/(drawer)/capture";

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  mockPhoto.mockResolvedValue({ uri: "letter", width: 1920, height: 2560 });
  mockPrepare.mockResolvedValue("full-page.jpg");
  mockEnqueue.mockResolvedValue(undefined);
});

it("takes a full-page contact photo into the editable review screen", async () => {
  const capture = { capture_id: 7, is_card: true, fields: { name: "Ann", kind: "document" } };
  mockCapture.mockResolvedValue(capture);
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(mockHandoff).toHaveBeenCalledWith("card", capture));
  expect(mockPrepare).toHaveBeenCalledWith({ uri: "letter", width: 1920, height: 2560 });
  expect(mockCapture).toHaveBeenCalledWith("full-page.jpg");
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/card-confirm");
});

it("offers the multiple-contact document scanner from the contact scanner", () => {
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("Scan a page with multiple contacts"));
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/scan-document");
});

it("retains the prepared photo for an offline retry", async () => {
  mockCapture.mockRejectedValue(new Error("offline"));
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("🖼  Choose from library"));
  await waitFor(() => expect(mockEnqueue).toHaveBeenCalledWith("full-page.jpg"));
  expect(mockHandoff).not.toHaveBeenCalled();
});

it("reports unreadable text without claiming it must be a business card", async () => {
  mockCapture.mockResolvedValue({ is_card: false, fields: {} });
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Couldn't read that",
    "No readable contact details found. Retake the photo with the text clearly visible."));
  expect(mockPush).not.toHaveBeenCalled();
});

it("reports camera permission failure without uploading or queueing", async () => {
  mockPhoto.mockRejectedValue(new Error("camera-permission"));
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Camera permission needed",
    "Enable camera access to scan contact details."));
  expect(mockCapture).not.toHaveBeenCalled();
  expect(mockEnqueue).not.toHaveBeenCalled();
});

it("does not queue a server rejection or upload a cancelled photo", async () => {
  mockCapture.mockRejectedValue({ response: { status: 413 } });
  const screen = render(<CaptureScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Upload failed", expect.any(String)));
  expect(mockEnqueue).not.toHaveBeenCalled();
  mockCapture.mockClear();
  mockPhoto.mockResolvedValue(null);
  fireEvent.press(screen.getByText("🖼  Choose from library"));
  await waitFor(() => expect(mockPhoto).toHaveBeenCalledWith("library"));
  expect(mockCapture).not.toHaveBeenCalled();
});
