jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

import * as SecureStore from "expo-secure-store";
import { getToken, saveToken, clearToken } from "../../services/auth";

const mockGet = SecureStore.getItemAsync as jest.Mock;
const mockSet = SecureStore.setItemAsync as jest.Mock;
const mockDel = SecureStore.deleteItemAsync as jest.Mock;

describe("auth service", () => {
  beforeEach(() => jest.clearAllMocks());

  it("getToken returns null when nothing stored", async () => {
    mockGet.mockResolvedValue(null);
    expect(await getToken()).toBeNull();
  });

  it("getToken returns stored token", async () => {
    mockGet.mockImplementation(async (key: string) => key === "engcrm_jwt" ? "my-token" : null);
    expect(await getToken()).toBe("my-token");
  });

  it("saveToken stores token and role", async () => {
    mockSet.mockResolvedValue(undefined);
    await saveToken("my-token", "admin");
    expect(mockSet).toHaveBeenCalledWith("engcrm_session", JSON.stringify({ token: "my-token", role: "admin", server: "production" }));
  });

  it("clearToken deletes both keys", async () => {
    mockDel.mockResolvedValue(undefined);
    await clearToken();
    expect(mockDel).toHaveBeenCalledWith("engcrm_jwt");
    expect(mockDel).toHaveBeenCalledWith("engcrm_role");
  });
});

describe("isolated reviewer sessions", () => {
  it("stores the reviewer token and destination together", async () => {
    mockSet.mockResolvedValue(undefined);
    await saveToken("review-token", "admin", "reviewer");
    expect(mockSet).toHaveBeenCalledWith("engcrm_session", JSON.stringify({ token: "review-token", role: "admin", server: "reviewer" }));
  });
});
