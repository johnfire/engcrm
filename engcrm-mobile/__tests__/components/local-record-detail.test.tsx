import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalRecordDetail } from "../../components/local-record-detail";
import { useOffline } from "../../services/offline-context";
import { readLocalWorkspace } from "../../services/local-records";

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }),
  useFocusEffect: (callback: () => void) => jest.requireActual("react").useEffect(callback, [callback]) }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/local-records", () => ({ readLocalWorkspace: jest.fn() }));
jest.mock("../../services/use-admin-role", () => ({ useAdminRole: () => true }));

it("shows an offline person's fields, deal and saved history", async () => {
  const record = (syncId: string, fields: Record<string, unknown>) => ({ syncId, fields, serverId: null,
    isLocalOnly: true, pendingCount: 1, failedCount: 0 });
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 1,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [], person: [record("person", { name: "Pat", phone: "123" })],
    deal: [record("deal", { person_sync_id: "person", offer_name: "Consulting", pipeline_stage: "prospect" })],
    person_note: [record("note", { person_sync_id: "person", note: "Met offline", occurred_at: "2026-11-25T10:00:00Z" })],
    organization_activity: [] });
  const view = render(<LocalRecordDetail kind="person" syncId="person" />);
  await waitFor(() => expect(view.getByText("Pat")).toBeTruthy());
  expect(view.getByText("123")).toBeTruthy();
  expect(view.getByText("Consulting")).toBeTruthy();
  expect(view.getByText("Met offline")).toBeTruthy();
  fireEvent.press(view.getByText("Edit"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-person", params: { sync_id: "person" } });
  fireEvent.press(view.getByText("Log a meeting"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/log-meeting",
    params: { kind: "person", sync_id: "person", name: "Pat" } });
});

it("shows the details of an offline activity, including the follow-up", async () => {
  const record = (syncId: string, fields: Record<string, unknown>) => ({ syncId, fields, serverId: null,
    isLocalOnly: true, pendingCount: 0, failedCount: 0 });
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 0,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [record("org", { name: "Company" })], person: [], deal: [],
    person_note: [], organization_activity: [record("activity", { organization_sync_id: "org", interaction_date: "2026-11-25",
      summary: "Agreed to talk", duration_minutes: 15, materials_left: "Flyer", next_action: "Send proposal" })] });
  const view = render(<LocalRecordDetail kind="organization" syncId="org" />);
  await waitFor(() => expect(view.getByText("Agreed to talk")).toBeTruthy());
  expect(view.getByText(/15 min/)).toBeTruthy();
  expect(view.getByText(/Flyer/)).toBeTruthy();
  expect(view.getByText(/Send proposal/)).toBeTruthy();
});

it("shows linked people and opens the offline add-person form from an organization", async () => {
  const record = (syncId: string, fields: Record<string, unknown>) => ({ syncId, fields, serverId: null,
    isLocalOnly: true, pendingCount: 0, failedCount: 0 });
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 0,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [record("org", { name: "Company" })],
    person: [record("p", { name: "Pat", organization_sync_id: "org" })], deal: [], person_note: [], organization_activity: [] });
  const view = render(<LocalRecordDetail kind="organization" syncId="org" />);
  await waitFor(() => expect(view.getByText("Pat")).toBeTruthy());
  fireEvent.press(view.getByText("Add person"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/edit-person",
    params: { offline_create: "1", organization_sync_id: "org" } });
});

it("opens the existing online detail for a synchronized record", async () => {
  const company = { syncId: "org-online", serverId: 42, isLocalOnly: false, pendingCount: 0, failedCount: 0,
    fields: { name: "Company" } };
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 0,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [company], person: [], deal: [], person_note: [], organization_activity: [] });
  const view = render(<LocalRecordDetail kind="organization" syncId="org-online" />);
  await waitFor(() => expect(view.getByText("More online options")).toBeTruthy());
  fireEvent.press(view.getByText("More online options"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/organization-detail", params: { id: "42" } });
});
