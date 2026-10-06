import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

const mockPush = jest.fn();
const mockPhoto = jest.fn();
const mockPrepare = jest.fn();
const mockCapture = jest.fn();
const mockEnqueue = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  useFocusEffect: () => {},
}));
jest.mock("../../services/documentPhoto", () => ({
  newDocumentBatchId: () => "page-batch",
  chooseDocumentPhoto: (...args: unknown[]) => mockPhoto(...args),
  prepareDocumentPhoto: (...args: unknown[]) => mockPrepare(...args),
}));
jest.mock("../../services/documentApi", () => ({
  captureDocument: (...args: unknown[]) => mockCapture(...args),
}));
jest.mock("../../services/cardQueue", () => ({
  enqueue: (...args: unknown[]) => mockEnqueue(...args),
  flush: jest.fn().mockResolvedValue({ remaining: 0 }),
  pendingCount: jest.fn().mockResolvedValue(0),
}));
import ScanDocumentScreen from "../../app/(drawer)/scan-document";

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  mockPhoto.mockResolvedValue({ uri: "original", width: 3000, height: 4000 });
  mockPrepare.mockResolvedValue("prepared");
  mockEnqueue.mockResolvedValue(undefined);
});

it("uploads the full page and offers review for every extracted draft", async () => {
  mockCapture.mockResolvedValue({ is_document: true, captures: [{ capture_id: 1 }, { capture_id: 2 }] });
  const screen = render(<ScanDocumentScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(mockCapture).toHaveBeenCalledWith("prepared", "page-batch"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Contacts ready for review",
    "2 contact drafts are ready. Review each before saving.", expect.any(Array)));
  const buttons = (Alert.alert as jest.Mock).mock.calls.at(-1)[2];
  buttons[0].onPress();
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/card-queue");
});

it("persists an offline page with its original batch ID", async () => {
  mockCapture.mockRejectedValue(new Error("offline"));
  const screen = render(<ScanDocumentScreen />);
  fireEvent.press(screen.getByText("🖼  Choose from library"));
  await waitFor(() => expect(mockEnqueue).toHaveBeenCalledWith("prepared", "document", "page-batch"));
  expect(mockPush).not.toHaveBeenCalled();
});

it("keeps unreadable pages out of the review queue", async () => {
  mockCapture.mockResolvedValue({ is_document: false, captures: [], note: "Retake this page" });
  const screen = render(<ScanDocumentScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Couldn't read that", "Retake this page"));
  expect(mockEnqueue).not.toHaveBeenCalled();
  expect(mockPush).not.toHaveBeenCalled();
});

it("does not queue a rejected server request", async () => {
  mockCapture.mockRejectedValue({ response: { status: 413 } });
  const screen = render(<ScanDocumentScreen />);
  fireEvent.press(screen.getByText("📷  Take photo"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith("Upload failed", expect.any(String)));
  expect(mockEnqueue).not.toHaveBeenCalled();
});
