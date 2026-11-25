import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalContactsScreen } from "../../components/local-contacts-screen";
import { useOffline } from "../../services/offline-context";
import { readLocalWorkspace } from "../../services/local-records";

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }),
  useFocusEffect: (callback: () => void) => jest.requireActual("react").useEffect(callback, [callback]) }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/local-records", () => ({ readLocalWorkspace: jest.fn() }));
jest.mock("../../hooks/useStoredSort", () => ({ useStoredSort: () => ({ sort: { key: "name", direction: "asc" }, ready: true, choose: jest.fn() }) }));

it("shows local contacts and navigates with their stable offline identity", async () => {
  const localRecord = (syncId: string, fields: Record<string, unknown>) => ({ syncId, fields, serverId: null,
    isLocalOnly: true, pendingCount: 1, failedCount: 0 });
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 1,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [localRecord("org-uuid", { name: "Company" })],
    person: [localRecord("person-uuid", { name: "Pat", organization_sync_id: "org-uuid" })],
    deal: [], organization_activity: [], person_note: [localRecord("note", { person_sync_id: "person-uuid",
      occurred_at: "2026-11-25T10:00:00Z", method: "visit" })] });
  const view = render(<LocalContactsScreen />);
  await waitFor(() => expect(view.getByText("Company")).toBeTruthy());
  fireEvent.press(view.getByText("Pat"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { sync_id: "person-uuid" } });
});

it("does not keep the previous account's contacts visible while another account opens", async () => {
  const database = {};
  const status = { ready: true, pending: 0, failed: 0, review: 0, lastSuccessAt: null, upToDate: false };
  const base = { status, state: "idle" as const, requestSync: jest.fn(), retryOpen: jest.fn(), refreshStatus: jest.fn() };
  jest.mocked(useOffline).mockReturnValue({ ...base, session: { database } as never });
  jest.mocked(readLocalWorkspace).mockResolvedValueOnce({ organization: [], person: [{ syncId: "private", serverId: 2,
    fields: { name: "Private person" }, isLocalOnly: false, pendingCount: 0, failedCount: 0 }],
    deal: [{ syncId: "deal", serverId: 3, fields: { person_sync_id: "private", status: "contacted" }, isLocalOnly: false,
      pendingCount: 0, failedCount: 0 }], person_note: [], organization_activity: [] });
  jest.mocked(readLocalWorkspace).mockReturnValueOnce(new Promise(() => {}));
  const view = render(<LocalContactsScreen />);
  await waitFor(() => expect(view.getByText("Private person")).toBeTruthy());
  jest.mocked(useOffline).mockReturnValue({ ...base, session: { database: {} } as never });
  view.rerender(<LocalContactsScreen />);
  expect(view.queryByText("Private person")).toBeNull();
});
