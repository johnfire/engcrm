const mockEndSession = jest.fn(async () => undefined);
const mockReplace = jest.fn();
jest.mock("expo-router", () => ({ router: { replace: (...args: unknown[]) => mockReplace(...args) } }));
jest.mock("../../services/session-end", () => ({ endSession: () => mockEndSession() }));

import { buildHeaders, API_BASE, client } from "../../services/api";

describe("api service", () => {
  it("uses the correct base URL", () => {
    expect(API_BASE).toBe("https://engcrm.christopherrehm.de");
  });

  it("buildHeaders includes Authorization when token provided", () => {
    const headers = buildHeaders("my-jwt-token");
    expect(headers["Authorization"]).toBe("Bearer my-jwt-token");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("buildHeaders works without token", () => {
    const headers = buildHeaders(null);
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["Authorization"]).toBeUndefined();
  });
});

describe("a revoked or expired token", () => {
  const rejectWith401 = (config: { url?: string }) =>
    Promise.reject(Object.assign(new Error("Unauthorized"), { config, response: { status: 401 }, isAxiosError: true }));

  beforeEach(() => {
    mockEndSession.mockClear();
    mockReplace.mockClear();
    client.defaults.adapter = rejectWith401 as never;
  });

  it("ends the session once for a burst of 401s, then sends the user to login", async () => {
    await Promise.allSettled([client.get("/api/a"), client.get("/api/b"), client.get("/api/c")]);
    expect(mockEndSession).toHaveBeenCalledTimes(1);
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });

  it("leaves the session alone when the login call itself is refused", async () => {
    await Promise.allSettled([client.post("/api/auth/token", {})]);
    expect(mockEndSession).not.toHaveBeenCalled();
  });
});
