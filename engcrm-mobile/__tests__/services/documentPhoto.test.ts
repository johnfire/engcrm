const mockPermission = jest.fn();
const mockCamera = jest.fn();
const mockLibrary = jest.fn();
const mockResize = jest.fn();
const mockSave = jest.fn().mockResolvedValue({ uri: "prepared.jpg" });
const mockRender = jest.fn().mockResolvedValue({ saveAsync: mockSave });
jest.mock("expo-image-picker", () => ({
  requestCameraPermissionsAsync: () => mockPermission(),
  launchCameraAsync: (...args: unknown[]) => mockCamera(...args),
  launchImageLibraryAsync: (...args: unknown[]) => mockLibrary(...args),
}));
jest.mock("expo-image-manipulator", () => ({
  ImageManipulator: { manipulate: () => ({ resize: mockResize, renderAsync: mockRender }) },
  SaveFormat: { JPEG: "jpeg" },
}));
import { chooseDocumentPhoto, newDocumentBatchId, prepareDocumentPhoto } from "../../services/documentPhoto";

beforeEach(() => jest.clearAllMocks());

it("preserves the whole page and returns the selected camera asset", async () => {
  const photo = { uri: "page.jpg", width: 3000, height: 4000 };
  mockPermission.mockResolvedValue({ granted: true });
  mockCamera.mockResolvedValue({ canceled: false, assets: [photo] });
  expect(await chooseDocumentPhoto("camera")).toEqual(photo);
  expect(mockCamera).toHaveBeenCalledWith(expect.objectContaining({ allowsEditing: false }));
});

it("rejects missing camera permission and handles picker cancellation", async () => {
  mockPermission.mockResolvedValue({ granted: false });
  await expect(chooseDocumentPhoto("camera")).rejects.toThrow("camera-permission");
  expect(mockCamera).not.toHaveBeenCalled();
  mockLibrary.mockResolvedValue({ canceled: true });
  expect(await chooseDocumentPhoto("library")).toBeNull();
});

it("limits the longest edge while keeping portrait pages legible", async () => {
  expect(await prepareDocumentPhoto({ uri: "page", width: 3000, height: 4000 })).toBe("prepared.jpg");
  expect(mockResize).toHaveBeenCalledWith({ height: 2048 });
  expect(mockSave).toHaveBeenCalledWith({ compress: 0.85, format: "jpeg" });
});

it("keeps landscape orientation and does not upscale smaller photos", async () => {
  await prepareDocumentPhoto({ uri: "page", width: 4000, height: 3000 });
  expect(mockResize).toHaveBeenCalledWith({ width: 2048 });
  mockResize.mockClear();
  await prepareDocumentPhoto({ uri: "page", width: 1000, height: 1500 });
  expect(mockResize).not.toHaveBeenCalled();
});

it("creates a reusable batch identifier for the upload and offline retry", () => {
  const first = newDocumentBatchId();
  expect(first).toMatch(/^[A-Za-z0-9-]{1,64}$/);
  expect(newDocumentBatchId()).not.toBe(first);
});
