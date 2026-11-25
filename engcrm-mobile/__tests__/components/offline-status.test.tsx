import { fireEvent, render } from "@testing-library/react-native";

import { OfflineStatus } from "../../components/offline-status";
import { useOffline } from "../../services/offline-context";

jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));

it("shows queued work and offers a manual sync", () => {
  const requestSync = jest.fn();
  jest.mocked(useOffline).mockReturnValue({ session: {} as never, state: "idle", requestSync, retryOpen: jest.fn(), refreshStatus: jest.fn(),
    status: { ready: true, pending: 2, failed: 1, review: 1, lastSuccessAt: null, upToDate: false } });
  const view = render(<OfflineStatus />);
  expect(view.getByText("2 waiting · 1 failed · 1 for review")).toBeTruthy();
  fireEvent.press(view.getByText("Sync now"));
  expect(requestSync).toHaveBeenCalledTimes(1);
});

it("shows nothing while the feature is disabled", () => {
  jest.mocked(useOffline).mockReturnValue({ session: null, status: null, state: "disabled", requestSync: jest.fn(),
    retryOpen: jest.fn(), refreshStatus: jest.fn() });
  expect(render(<OfflineStatus />).toJSON()).toBeNull();
});
