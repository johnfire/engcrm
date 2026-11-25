import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalRatings } from "../../components/local-ratings";
import { queueLocalUpdate } from "../../services/local-outbox";
import { useOffline } from "../../services/offline-context";

jest.mock("expo-crypto", () => ({ randomUUID: () => "fb4fa281-8a94-4726-9ce7-02c18c90aa91" }));
jest.mock("../../services/local-outbox", () => ({ queueLocalUpdate: jest.fn() }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: async () => "fb4fa281-8a94-4726-9ce7-02c18c90aa92" }));

it("queues a private person rating for the current account", async () => {
  const database = {};
  const requestSync = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync,
    refreshStatus: jest.fn(async () => {}), retryOpen: jest.fn() });
  const item = { syncId: "person", serverId: null, isLocalOnly: false, pendingCount: 0, failedCount: 0, fields: {} };
  const view = render(<LocalRatings item={item} kind="person" />);
  fireEvent.press(view.getByText("1 Exceptional"));
  await waitFor(() => expect(queueLocalUpdate).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "person", entitySyncId: "person", patch: { value_rating: 1 } })));
  expect(requestSync).toHaveBeenCalled();
});
