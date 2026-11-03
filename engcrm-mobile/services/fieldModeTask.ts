// The background task field mode runs. TaskManager needs it defined in the bundle's
// global scope, before any screen mounts, so app/_layout.tsx imports this file first
// (Expo SDK 56 docs, expo-task-manager).
import type { LocationObject } from "expo-location";
import * as TaskManager from "expo-task-manager";

import { FIELD_TASK, handleLocations } from "./fieldMode";

TaskManager.defineTask<{ locations: LocationObject[] }>(FIELD_TASK, async ({ data, error }) => {
  if (error || !data?.locations?.length) return;
  await handleLocations(data.locations);
});
