import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalActivityForm } from "../../components/local-activity-form";
import { openActivityDraft, saveActivityDraft } from "../../services/local-activity-drafts";
import { queueLocalActivity } from "../../services/local-outbox";
import { useOffline } from "../../services/offline-context";

const mockBack = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ back: mockBack }) }));
jest.mock("expo-crypto", () => ({ randomUUID: jest.fn(() => "fb4fa281-8a94-4726-9ce7-02c18c90aa91") }));
jest.mock("../../services/local-activity-drafts", () => ({ openActivityDraft: jest.fn(), saveActivityDraft: jest.fn() }));
jest.mock("../../services/local-outbox", () => ({ queueLocalActivity: jest.fn() }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: jest.fn(async () => "fb4fa281-8a94-4726-9ce7-02c18c90aa92") }));
jest.mock("../../services/use-admin-role", () => ({ useAdminRole: () => true }));
jest.mock("../../hooks/useLocalOffers", () => ({ useLocalOffers: () => [] }));

it("restores a draft, saves it locally and asks the sync worker to send it", async () => {
  const database = {};
  const requestSync = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync,
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  jest.mocked(openActivityDraft).mockResolvedValue({ id: "draft-id", values: { note: "Earlier text" } });
  jest.mocked(saveActivityDraft).mockResolvedValue();
  const view = render(<LocalActivityForm kind="person" syncId="person-id" />);
  await waitFor(() => expect(view.getByDisplayValue("Earlier text")).toBeTruthy());
  fireEvent.changeText(view.getByDisplayValue("Earlier text"), "Met offline");
  fireEvent.press(view.getByText("Save note"));
  await waitFor(() => expect(queueLocalActivity).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "person_note", draftId: "draft-id", patch: expect.objectContaining({
      person_sync_id: "person-id", note: "Met offline",
    }) })));
  expect(requestSync).toHaveBeenCalled();
  expect(mockBack).toHaveBeenCalled();
});
