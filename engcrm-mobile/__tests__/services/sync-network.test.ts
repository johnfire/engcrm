import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import axios from "axios";

import { client } from "../../services/api";
import { getSession } from "../../services/auth";
import { BootstrapExpiredError } from "../../services/sync-bootstrap-worker";
import { fetchSyncIdentity, getSyncDeviceId, requestBootstrapPage, requestPushBatch } from "../../services/sync-network";

jest.mock("../../services/api", () => ({ client: { get: jest.fn(), post: jest.fn() } }));
jest.mock("../../services/auth", () => ({ getSession: jest.fn() }));
jest.mock("axios", () => ({ __esModule: true, default: { create: jest.fn() } }));
jest.mock("expo-crypto", () => ({ randomUUID: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(axios.create).mockReturnValue(client as never);
  jest.mocked(getSession).mockResolvedValue({ token: "verified-token", role: "admin", server: "production" });
});

it("uses a server-verified account and workspace identity", async () => {
  jest.mocked(getSession).mockResolvedValueOnce({ token: "verified-token", role: "admin", server: "reviewer" })
    .mockResolvedValueOnce({ token: "verified-token", role: "admin", server: "reviewer" });
  jest.mocked(client.get).mockResolvedValueOnce({ data: { user_id: 12, workspace_id: 3 } });
  await expect(fetchSyncIdentity("reviewer")).resolves.toEqual({ environment: "reviewer", userId: 12, workspaceId: 3 });
  expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({ baseURL: expect.stringContaining("/reviewer"),
    headers: expect.objectContaining({ Authorization: "Bearer verified-token" }) }));
  jest.mocked(client.get).mockResolvedValueOnce({ data: { user_id: 12, workspace_id: null } });
  await expect(fetchSyncIdentity("production")).rejects.toThrow("identity");
});

it("rejects an identity if the account changes while the request is in flight", async () => {
  jest.mocked(getSession).mockResolvedValueOnce({ token: "first", role: "admin", server: "production" })
    .mockResolvedValueOnce({ token: "second", role: "admin", server: "production" });
  jest.mocked(client.get).mockResolvedValueOnce({ data: { user_id: 12, workspace_id: 3 } });
  await expect(fetchSyncIdentity("production")).rejects.toThrow("session changed");
});

it("turns a single ID reuse conflict into an explicit failed outcome", async () => {
  jest.mocked(client.post).mockRejectedValueOnce({ response: { status: 409 } });
  await expect(requestPushBatch("production", [{ mutation_id: "one" }])).resolves.toEqual({
    outcomes: [{ mutation_id: "one", status: "conflict", entity: null }],
  });
});

it("generates one stable installation identifier even with concurrent requests", async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  jest.mocked(Crypto.randomUUID).mockReturnValue("fb4fa281-8a94-4726-9ce7-02c18c90aa90");
  const ids = await Promise.all([getSyncDeviceId(), getSyncDeviceId()]);
  expect(ids).toEqual(["fb4fa281-8a94-4726-9ce7-02c18c90aa90", "fb4fa281-8a94-4726-9ce7-02c18c90aa90"]);
  expect(SecureStore.setItemAsync).toHaveBeenCalledTimes(1);
});

it("distinguishes an expired bootstrap from a token belonging to another device", async () => {
  jest.mocked(client.get).mockRejectedValueOnce({ response: { status: 400, data: { detail: "Bootstrap token has expired" } } });
  await expect(requestBootstrapPage("id", "production", "token")).rejects.toBeInstanceOf(BootstrapExpiredError);
  jest.mocked(client.get).mockRejectedValueOnce({ response: { status: 400, data: { detail: "Bootstrap token belongs to another account or device" } } });
  await expect(requestBootstrapPage("id", "production", "token")).rejects.not.toBeInstanceOf(BootstrapExpiredError);
});
