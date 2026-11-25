import { getSession } from "../../services/auth";
import { createBoundSyncNetwork } from "../../services/bound-sync-network";
import { synchronizeOfflineSession } from "../../services/offline-sync-session";
import { synchronizeCycle } from "../../services/sync-cycle";
import { loadVerifiedIdentity } from "../../services/sync-identity-cache";
import { getSyncDeviceId } from "../../services/sync-network";

jest.mock("../../services/auth", () => ({ getSession: jest.fn() }));
jest.mock("../../services/bound-sync-network", () => ({ createBoundSyncNetwork: jest.fn() }));
jest.mock("../../services/sync-cycle", () => ({ synchronizeCycle: jest.fn() }));
jest.mock("../../services/sync-identity-cache", () => ({ loadVerifiedIdentity: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ getSyncDeviceId: jest.fn() }));

const identity = { environment: "production" as const, workspaceId: 3, userId: 5 };
const offline = { identity, database: {} as never };

beforeEach(() => {
  jest.resetAllMocks();
  jest.mocked(getSession).mockResolvedValue({ token: "token", role: "admin", server: "production" });
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(identity);
  jest.mocked(getSyncDeviceId).mockResolvedValue("device");
});

it("uses a network worker bound to the verified account", async () => {
  const network = {} as never;
  jest.mocked(createBoundSyncNetwork).mockReturnValue(network);
  await synchronizeOfflineSession(offline, "1.0");
  expect(createBoundSyncNetwork).toHaveBeenCalledWith("token", "production", "device", "1.0");
  expect(synchronizeCycle).toHaveBeenCalledWith(offline.database, "device", network);
});

it("does not send a database belonging to another account", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue({ ...identity, userId: 6 });
  await expect(synchronizeOfflineSession(offline, "1.0")).rejects.toThrow("account");
  expect(synchronizeCycle).not.toHaveBeenCalled();
});
