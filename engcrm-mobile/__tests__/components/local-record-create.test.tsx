import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalRecordCreate } from "../../components/local-record-create";
import { useOffline } from "../../services/offline-context";
import { queueLocalCreate, queueLocalCreateWithInitialDeal } from "../../services/local-outbox";

const mockReplace = jest.fn();
let mockOffers = [{ id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" },
  { id: 2, slug: "training", name: "Training", website: null, revenue_kind: "one_off" }];
jest.mock("expo-router", () => ({ useRouter: () => ({ replace: mockReplace }) }));
jest.mock("expo-crypto", () => ({ randomUUID: jest.fn(() => "fb4fa281-8a94-4726-9ce7-02c18c90aa91") }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/local-outbox", () => ({ queueLocalCreate: jest.fn(), queueLocalCreateWithInitialDeal: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: jest.fn(async () => "fb4fa281-8a94-4726-9ce7-02c18c90aa92") }));
jest.mock("../../services/use-admin-role", () => ({ useAdminRole: () => true }));
jest.mock("../../hooks/useLocalOffers", () => ({ useLocalOffers: () => mockOffers }));

it("creates an organization and its initial deal in one offline operation", async () => {
  const database = {};
  const requestSync = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync,
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  const view = render(<LocalRecordCreate kind="organization" />);
  fireEvent.changeText(view.getByLabelText("Name"), "Company");
  fireEvent.press(view.getByText("Add business"));
  await waitFor(() => expect(queueLocalCreateWithInitialDeal).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "organization", patch: { name: "Company" } }),
    expect.objectContaining({ offerSlug: "consulting", stage: "candidate", status: "none" })));
  expect(requestSync).toHaveBeenCalled();
  expect(mockReplace).toHaveBeenCalledWith(expect.objectContaining({ pathname: "/(drawer)/organization-detail" }));
});

it("creates a person linked to a local organization without requiring a deal", async () => {
  const database = {};
  jest.mocked(useOffline).mockReturnValue({ session: { database } as never, status: null, state: "idle", requestSync: jest.fn(),
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  const view = render(<LocalRecordCreate kind="person" organizationSyncId="org-uuid" />);
  fireEvent.changeText(view.getByLabelText("Name"), "Pat");
  fireEvent.press(view.getByText("Add person"));
  await waitFor(() => expect(queueLocalCreate).toHaveBeenCalledWith(database,
    expect.objectContaining({ entityKind: "person", patch: { name: "Pat", organization_sync_id: "org-uuid" } })));
});

it("preserves unsaved text when a selected offer is archived", () => {
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: null, state: "idle", requestSync: jest.fn(),
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
  const view = render(<LocalRecordCreate kind="organization" />);
  fireEvent.changeText(view.getByLabelText("Name"), "Still editing");
  fireEvent.press(view.getByText("Training"));
  mockOffers = [mockOffers[0]];
  view.rerender(<LocalRecordCreate kind="organization" />);
  expect(view.getByDisplayValue("Still editing")).toBeTruthy();
  expect(view.getByText("That offer is no longer available. Choose another offer before saving.")).toBeTruthy();
});
