import AsyncStorage from "@react-native-async-storage/async-storage";

const mockPost = jest.fn();
jest.mock("../../services/api", () => ({ client: { post: (...a: any[]) => mockPost(...a) } }));

jest.mock("expo-location", () => ({
  __esModule: true,
  requestForegroundPermissionsAsync: jest.fn(),
  requestBackgroundPermissionsAsync: jest.fn(),
  startLocationUpdatesAsync: jest.fn(),
  stopLocationUpdatesAsync: jest.fn(),
  hasStartedLocationUpdatesAsync: jest.fn(),
  Accuracy: { High: 4 },
}));
import * as ExpoLocation from "expo-location";
const mockLocation = ExpoLocation as unknown as Record<string, jest.Mock>;

import {
  enqueue,
  FIELD_TASK,
  fieldModeEndsAt,
  flushQueue,
  handleLocations,
  startFieldMode,
  stopFieldMode,
  toPoints,
} from "../../services/fieldMode";

const fix = (minute: number, latitude = 48.05) => ({
  coords: { latitude, longitude: 10.87, accuracy: 8, altitude: null, altitudeAccuracy: null, heading: null, speed: null },
  timestamp: Date.UTC(2026, 10, 3, 12, minute),
});

async function queued(): Promise<any[]> {
  return JSON.parse((await AsyncStorage.getItem("field_points_v1")) ?? "[]");
}

beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  mockPost.mockResolvedValue({ data: { stored: 1 } });
  mockLocation.hasStartedLocationUpdatesAsync.mockResolvedValue(true);
});

it("turns a location into a point the server takes", () => {
  expect(toPoints([fix(5)])).toEqual([
    { latitude: 48.05, longitude: 10.87, accuracy_m: 8, recorded_at: "2026-11-03T12:05:00.000Z" },
  ]);
});

it("sends queued points and empties the queue", async () => {
  await enqueue(toPoints([fix(0), fix(5)]));
  expect(await flushQueue()).toBe(2);
  expect(mockPost).toHaveBeenCalledWith("/api/me/locations", { points: toPoints([fix(0), fix(5)]) });
  expect(await queued()).toEqual([]);
});

it("keeps every point while offline, and sends them all once back online", async () => {
  mockPost.mockRejectedValue(new Error("Network Error"));
  await handleLocations([fix(0)], Date.UTC(2026, 10, 3, 12, 0));
  await handleLocations([fix(5)], Date.UTC(2026, 10, 3, 12, 5));
  expect(await queued()).toHaveLength(2);

  mockPost.mockResolvedValue({ data: { stored: 2 } });
  expect(await flushQueue()).toBe(2);
  expect(await queued()).toEqual([]);
});

it("sends at most 500 per request, and never resends a batch that went through", async () => {
  const many = Array.from({ length: 1200 }, (_, i) => ({ latitude: 48, longitude: 10, accuracy_m: null,
    recorded_at: new Date(Date.UTC(2026, 10, 1) + i * 300000).toISOString() }));
  await enqueue(many);
  mockPost.mockResolvedValueOnce({}).mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("offline"));
  expect(await flushQueue()).toBe(1000);
  expect(mockPost.mock.calls.map((call) => call[1].points.length)).toEqual([500, 500, 200]);
  const left = await queued();
  expect(left).toHaveLength(200);
  expect(left[0]).toEqual(many[1000]); // the third batch, still waiting
});

it("switches itself off after 8 hours, sending what it recorded", async () => {
  await AsyncStorage.setItem("field_mode_started_at", String(Date.UTC(2026, 10, 3, 8, 0)));
  await handleLocations([fix(0)], Date.UTC(2026, 10, 3, 15, 59)); // 7 h 59 min: still on
  expect(mockLocation.stopLocationUpdatesAsync).not.toHaveBeenCalled();
  await handleLocations([fix(1)], Date.UTC(2026, 10, 3, 16, 1)); // 8 h 1 min
  expect(mockLocation.stopLocationUpdatesAsync).toHaveBeenCalledWith(FIELD_TASK);
  expect(await fieldModeEndsAt()).toBeNull();
  expect(mockPost).toHaveBeenCalled();
});

describe("turning it on", () => {
  const texts = { title: "EngCRM field mode", body: "Recording" };

  it("asks for location while using the app only, then records every 5 minutes", async () => {
    mockLocation.requestForegroundPermissionsAsync.mockResolvedValue({ granted: true });
    expect(await startFieldMode(texts)).toBe("started");
    // A foreground service with a notification needs no "all the time" permission.
    expect(mockLocation.requestBackgroundPermissionsAsync).not.toHaveBeenCalled();
    const [task, options] = mockLocation.startLocationUpdatesAsync.mock.calls[0];
    expect(task).toBe(FIELD_TASK);
    expect(options).toMatchObject({
      timeInterval: 300000, distanceInterval: 0, accuracy: 4,
      foregroundService: { notificationTitle: "EngCRM field mode", notificationBody: "Recording" },
    });
    expect(await fieldModeEndsAt()).not.toBeNull();
  });

  it("does not start without location", async () => {
    mockLocation.requestForegroundPermissionsAsync.mockResolvedValue({ granted: false });
    expect(await startFieldMode(texts)).toBe("location-denied");
    expect(mockLocation.startLocationUpdatesAsync).not.toHaveBeenCalled();
    expect(await fieldModeEndsAt()).toBeNull();
  });
});

it("turning it off stops recording and sends what is queued", async () => {
  await enqueue(toPoints([fix(0)]));
  await stopFieldMode();
  expect(mockLocation.stopLocationUpdatesAsync).toHaveBeenCalledWith(FIELD_TASK);
  expect(await queued()).toEqual([]);
});
