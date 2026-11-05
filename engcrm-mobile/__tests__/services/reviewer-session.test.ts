import * as SecureStore from "expo-secure-store";
import { AxiosAdapter } from "axios";
import { client, login } from "../../services/api";
import { saveToken } from "../../services/auth";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(), setItemAsync: jest.fn(), deleteItemAsync: jest.fn(),
}));

describe("reviewer sign-in", () => {
  const stored = new Map<string, string>();
  const destinations: { baseURL?: string; authorization?: string }[] = [];
  const previousAdapter = client.defaults.adapter;
  beforeEach(() => {
    stored.clear();
    destinations.length = 0;
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key: string) => stored.get(key) ?? null);
    (SecureStore.setItemAsync as jest.Mock).mockImplementation(async (key: string, value: string) => { stored.set(key, value); });
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementation(async (key: string) => { stored.delete(key); });
    client.defaults.adapter = (async (config) => {
      destinations.push({ baseURL: config.baseURL, authorization: config.headers.Authorization as string | undefined });
      return { config, data: { token: "test-token", role: "admin" }, status: 200, statusText: "OK", headers: {} };
    }) as AxiosAdapter;
  });
  afterAll(() => { client.defaults.adapter = previousAdapter; });

  it.each([
    ["tester367google@example.test", "https://engcrm.christopherrehm.de/reviewer"],
    ["person@example.test", "https://engcrm.christopherrehm.de"],
  ])("keeps the %s session on its chosen server after login", async (email, destination) => {
    const session = await login(email, "password");
    await saveToken(session.token, session.role, session.server);
    await client.get("/api/auth/me");
    expect(destinations).toEqual([
      { baseURL: destination, authorization: undefined },
      { baseURL: destination, authorization: "Bearer test-token" },
    ]);
  });
});
