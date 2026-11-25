import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

import { LogoutButton } from "../../app/(drawer)/_layout";
import { clearToken } from "../../services/auth";
import { useOffline } from "../../services/offline-context";
import { readSyncStatus } from "../../services/sync-status";

jest.mock("expo-router/drawer", () => {
  const Drawer: any = () => null;
  Drawer.Screen = () => null;
  return { Drawer, DrawerContentScrollView: () => null, DrawerItemList: () => null };
});
jest.mock("expo-router", () => ({ useRouter: () => ({ replace: jest.fn() }) }));
jest.mock("../../services/auth", () => ({ clearToken: jest.fn() }));
jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn(), OfflineProvider: ({ children }: any) => children }));
jest.mock("../../services/sync-status", () => ({ readSyncStatus: jest.fn() }));

it("asks before signing out with pending changes and keeps local data", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: null, state: "idle",
    requestSync: jest.fn(), refreshStatus: jest.fn(), retryOpen: jest.fn() });
  jest.mocked(readSyncStatus).mockResolvedValue({ ready: true, pending: 1, failed: 1, review: 0, lastSuccessAt: null, upToDate: false });
  const view = render(<LogoutButton />);
  fireEvent.press(view.getByText("Log out"));
  await waitFor(() => expect(alert).toHaveBeenCalled());
  expect(clearToken).not.toHaveBeenCalled();
  const buttons = alert.mock.calls[0][2]!;
  await buttons.find((button) => button.text === "Sign out and keep edits")!.onPress!();
  expect(clearToken).toHaveBeenCalledTimes(1);
  alert.mockRestore();
});
