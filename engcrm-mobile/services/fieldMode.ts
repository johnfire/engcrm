// Field mode: while it is on, the phone records where the user is every few minutes,
// in the background, and sends the points to the server (POST /api/me/locations), so
// Claude can find the business they stand in front of and they keep a travel history.
// See docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md.
//
// It runs as an Android foreground service with a notification, started from the switch
// while the app is open: that keeps it recording while the user talks in another app
// (Claude) without the "location all the time" permission, which Google Play reviews
// separately (expo-location's LocationModule.startLocationUpdatesAsync allows exactly this).
//
// Points go into a queue on the phone first and leave it only once the server has them,
// so a dead zone loses nothing; the server stores a point sent twice once, so a retry is
// always safe. Field mode switches itself off after FIELD_MODE_HOURS.
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";

import { client } from "./api";

export const FIELD_TASK = "engcrm-field-mode";
export const FIELD_MODE_HOURS = 8;
export const POINT_EVERY_MS = 5 * 60 * 1000;
const QUEUE_KEY = "field_points_v1";
const STARTED_KEY = "field_mode_started_at";
const MAX_QUEUE = 5000; // about 17 days of points: past that, the oldest go first
const MAX_UPLOAD = 500; // the server's batch limit

export interface FieldPoint {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  recorded_at: string; // ISO with time zone
}

export function toPoints(locations: Location.LocationObject[]): FieldPoint[] {
  return locations.map((location) => ({
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
    accuracy_m: location.coords.accuracy ?? null,
    recorded_at: new Date(location.timestamp).toISOString(),
  }));
}

async function readQueue(): Promise<FieldPoint[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeQueue(points: FieldPoint[]): Promise<void> {
  try {
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(points.slice(-MAX_QUEUE)));
  } catch {
    // storage full or unavailable: the points still in memory are tried this time
  }
}

export async function enqueue(points: FieldPoint[]): Promise<void> {
  if (points.length) await writeQueue([...(await readQueue()), ...points]);
}

/** Send what is queued, oldest first, in batches; keep whatever did not get through.
 *  Returns how many points left the phone. */
export async function flushQueue(): Promise<number> {
  let queue = await readQueue();
  let sent = 0;
  while (queue.length) {
    const batch = queue.slice(0, MAX_UPLOAD);
    try {
      await client.post("/api/me/locations", { points: batch });
    } catch {
      break; // offline or refused: try again with the next point
    }
    sent += batch.length;
    queue = queue.slice(batch.length);
    // Write after each batch, so a later failure never resends what already went.
    await writeQueue(queue);
  }
  return sent;
}

/** What the background task does with each delivery of locations. */
export async function handleLocations(locations: Location.LocationObject[], now: number = Date.now()): Promise<void> {
  await enqueue(toPoints(locations));
  await flushQueue();
  if (await expired(now)) await stopFieldMode();
}

async function expired(now: number): Promise<boolean> {
  const started = Number(await AsyncStorage.getItem(STARTED_KEY).catch(() => null));
  return !!started && now - started > FIELD_MODE_HOURS * 60 * 60 * 1000;
}

export type StartResult = "started" | "location-denied";

/** Ask for location (while using the app) and start recording. `texts` is the notification
 *  Android shows the whole time field mode is on. Call it from the open app: Android only
 *  lets a location service start in the foreground. */
export async function startFieldMode(texts: { title: string; body: string }): Promise<StartResult> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return "location-denied";
  await AsyncStorage.setItem(STARTED_KEY, String(Date.now()));
  await Location.startLocationUpdatesAsync(FIELD_TASK, {
    accuracy: Location.Accuracy.High, // a shop front, not a district
    timeInterval: POINT_EVERY_MS,
    distanceInterval: 0, // a point every 5 minutes even when standing still
    foregroundService: { notificationTitle: texts.title, notificationBody: texts.body, notificationColor: "#7c6fff" },
    pausesUpdatesAutomatically: false,
  });
  return "started";
}

export async function stopFieldMode(): Promise<void> {
  if (await Location.hasStartedLocationUpdatesAsync(FIELD_TASK).catch(() => false)) {
    await Location.stopLocationUpdatesAsync(FIELD_TASK);
  }
  await AsyncStorage.removeItem(STARTED_KEY).catch(() => undefined);
  await flushQueue(); // what was recorded still goes to the server
}

export async function isFieldModeOn(): Promise<boolean> {
  return Location.hasStartedLocationUpdatesAsync(FIELD_TASK).catch(() => false);
}

/** When field mode switches itself off; null when it is off. */
export async function fieldModeEndsAt(): Promise<Date | null> {
  const started = Number(await AsyncStorage.getItem(STARTED_KEY).catch(() => null));
  return started ? new Date(started + FIELD_MODE_HOURS * 60 * 60 * 1000) : null;
}
