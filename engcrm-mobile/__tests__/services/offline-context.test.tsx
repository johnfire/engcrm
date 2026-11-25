import { render, screen, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import { OfflineProvider, useOffline } from "../../services/offline-context";
import { openOfflineSession } from "../../services/offline-session";
import { synchronizeOfflineSession } from "../../services/offline-sync-session";
import { readSyncStatus } from "../../services/sync-status";

jest.mock("expo-network", () => ({ addNetworkStateListener: jest.fn(() => ({ remove: jest.fn() })) }));
jest.mock("../../services/offline-session", () => ({ openOfflineSession: jest.fn() }));
jest.mock("../../services/offline-sync-session", () => ({ synchronizeOfflineSession: jest.fn() }));
jest.mock("../../services/sync-status", () => ({ readSyncStatus: jest.fn() }));

function Consumer() {
  const offline = useOffline();
  return <Text>{offline.session ? "local-ready" : "local-loading"}</Text>;
}

beforeEach(() => jest.clearAllMocks());

it("exposes the local account without waiting for synchronization", async () => {
  const offline = { identity: { environment: "production", workspaceId: 1, userId: 2 }, database: {} };
  jest.mocked(openOfflineSession).mockResolvedValue(offline as never);
  jest.mocked(synchronizeOfflineSession).mockReturnValue(new Promise(() => {}));
  jest.mocked(readSyncStatus).mockResolvedValue({ ready: true, pending: 0, failed: 0, review: 0, lastSuccessAt: null, upToDate: false });
  const view = render(<OfflineProvider enabled><Consumer /></OfflineProvider>);
  await waitFor(() => expect(screen.getByText("local-ready")).toBeTruthy());
  expect(synchronizeOfflineSession).toHaveBeenCalled();
  view.unmount();
});

it("does not open a database while the feature is disabled", () => {
  render(<OfflineProvider enabled={false}><Consumer /></OfflineProvider>);
  expect(openOfflineSession).not.toHaveBeenCalled();
});
