import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { LocalEntitiesScreen } from "../../components/local-entities-screen";
import { useOffline } from "../../services/offline-context";
import { readLocalWorkspace } from "../../services/local-records";

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }),
  useFocusEffect: (callback: () => void) => jest.requireActual("react").useEffect(callback, [callback]) }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/local-records", () => ({ readLocalWorkspace: jest.fn() }));
jest.mock("../../hooks/useStoredSort", () => ({ useStoredSort: () => ({ sort: { key: "name", direction: "asc" }, ready: true, choose: jest.fn() }) }));

it("shows uncontacted local people and opens them by stable identity", async () => {
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: { ready: true, pending: 0,
    failed: 0, review: 0, lastSuccessAt: null, upToDate: false }, state: "idle", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  jest.mocked(readLocalWorkspace).mockResolvedValue({ organization: [], person: [{ syncId: "person-uuid", serverId: null,
    isLocalOnly: true, fields: { name: "Pat" }, pendingCount: 1, failedCount: 0 }], deal: [], person_note: [], organization_activity: [] });
  const view = render(<LocalEntitiesScreen kind="person" />);
  await waitFor(() => expect(view.getByText("Pat")).toBeTruthy());
  fireEvent.press(view.getByText("Pat"));
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/(drawer)/person-detail", params: { sync_id: "person-uuid" } });
});
