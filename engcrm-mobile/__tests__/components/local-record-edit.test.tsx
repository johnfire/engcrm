import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalRecordEdit } from "../../components/local-record-edit";
import { useOffline } from "../../services/offline-context";
import { queueLocalUpdate } from "../../services/local-outbox";
import { readLocalRecord } from "../../services/local-records";

const mockBack = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ back: mockBack }) }));
jest.mock("expo-crypto", () => ({ randomUUID: jest.fn(() => "fb4fa281-8a94-4726-9ce7-02c18c90aa91") }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/local-records", () => ({ readLocalRecord: jest.fn() }));
jest.mock("../../services/local-outbox", () => ({ queueLocalUpdate: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: jest.fn(async () => "fb4fa281-8a94-4726-9ce7-02c18c90aa92") }));
jest.mock("../../services/use-admin-role", () => ({ useAdminRole: () => true }));

it("saves an ordinary edit locally and asks the sync worker to send it", async () => {
  const database = {};
  const requestSync = jest.fn();
  const refreshStatus = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync,
    refreshStatus, retryOpen: jest.fn() });
  jest.mocked(readLocalRecord).mockResolvedValue({ syncId: "person", serverId: null, isLocalOnly: true,
    fields: { name: "Pat", phone: "old" }, pendingCount: 1, failedCount: 0 });
  const view = render(<LocalRecordEdit kind="person" syncId="person" />);
  await waitFor(() => expect(view.getByDisplayValue("old")).toBeTruthy());
  fireEvent.changeText(view.getByLabelText("Phone"), "123");
  fireEvent.press(view.getByText("Save"));
  await waitFor(() => expect(queueLocalUpdate).toHaveBeenCalledWith(database, expect.objectContaining({
    entityKind: "person", entitySyncId: "person", patch: { phone: "123" },
  })));
  expect(requestSync).toHaveBeenCalled();
  expect(mockBack).toHaveBeenCalled();
});
