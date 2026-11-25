import axios from "axios";

import { getSession } from "../../services/auth";
import { createBoundSyncNetwork } from "../../services/bound-sync-network";

jest.mock("../../services/auth", () => ({ getSession: jest.fn() }));
jest.mock("axios", () => ({ __esModule: true, default: { create: jest.fn() } }));

beforeEach(() => jest.resetAllMocks());

it("uses the verified account's token and environment for every sync request", async () => {
  const transport = { get: jest.fn(), post: jest.fn().mockResolvedValue({ data: { protocol_version: 1, bootstrap_required: true } }) };
  jest.mocked(axios.create).mockReturnValue(transport as never);
  jest.mocked(getSession).mockResolvedValue({ token: "original", role: "admin", server: "reviewer" });
  const network = createBoundSyncNetwork("original", "reviewer", "device", "1.0");
  await network.register();
  expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({ baseURL: expect.stringContaining("/reviewer"),
    headers: expect.objectContaining({ Authorization: "Bearer original" }) }));
  expect(transport.post).toHaveBeenCalledWith("/api/sync/devices", expect.objectContaining({ device_id: "device" }));
});

it("does not issue a request after the signed-in account changes", async () => {
  const transport = { get: jest.fn(), post: jest.fn() };
  jest.mocked(axios.create).mockReturnValue(transport as never);
  jest.mocked(getSession).mockResolvedValue({ token: "different", role: "admin", server: "production" });
  const network = createBoundSyncNetwork("original", "production", "device", "1.0");
  await expect(network.pull(0)).rejects.toThrow("session changed");
  expect(transport.get).not.toHaveBeenCalled();
});

it("does not accept a response after the signed-in account changes", async () => {
  const transport = { get: jest.fn().mockResolvedValue({ data: {} }), post: jest.fn() };
  jest.mocked(axios.create).mockReturnValue(transport as never);
  jest.mocked(getSession).mockResolvedValueOnce({ token: "original", role: "admin", server: "production" })
    .mockResolvedValueOnce({ token: "different", role: "admin", server: "production" });
  const network = createBoundSyncNetwork("original", "production", "device", "1.0");
  await expect(network.pull(0)).rejects.toThrow("session changed");
});
