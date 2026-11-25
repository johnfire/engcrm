import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalDealCard } from "../../components/local-deal-card";
import { queueLocalUpdate } from "../../services/local-outbox";
import { useOffline } from "../../services/offline-context";

jest.mock("expo-crypto", () => ({ randomUUID: jest.fn(() => "fb4fa281-8a94-4726-9ce7-02c18c90aa91") }));
jest.mock("../../services/local-outbox", () => ({ queueLocalUpdate: jest.fn() }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: jest.fn(async () => "fb4fa281-8a94-4726-9ce7-02c18c90aa92") }));

it("queues a deal stage change on the phone", async () => {
  const database = {};
  const requestSync = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync,
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  const deal = { syncId: "deal", serverId: null, isLocalOnly: true, pendingCount: 0, failedCount: 0,
    fields: { offer_name: "Consulting", pipeline_stage: "candidate", status: "none" } };
  const view = render(<LocalDealCard deal={deal} canEdit />);
  fireEvent.press(view.getByText("Prospect"));
  await waitFor(() => expect(queueLocalUpdate).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "deal", entitySyncId: "deal", patch: expect.objectContaining({ pipeline_stage: "prospect" }) })));
  expect(requestSync).toHaveBeenCalled();
});

it("queues the next step without requiring a server connection", async () => {
  const database = {};
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync: jest.fn(),
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  const deal = { syncId: "deal-next", serverId: null, isLocalOnly: true, pendingCount: 0, failedCount: 0,
    fields: { offer_name: "Consulting", pipeline_stage: "candidate", status: "none" } };
  const view = render(<LocalDealCard deal={deal} canEdit />);
  fireEvent.press(view.getByText("Add next step"));
  fireEvent.changeText(view.getByLabelText("What happens next"), "Send proposal");
  fireEvent.press(view.getByText("Save"));
  await waitFor(() => expect(queueLocalUpdate).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "deal", entitySyncId: "deal-next",
      patch: { next_step: "Send proposal", next_step_date: null } })));
});
