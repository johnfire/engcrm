import * as SecureStore from "expo-secure-store";
import { Server, serverForSession } from "./reviewer-routing";

const TOKEN_KEY = "engcrm_jwt";
const ROLE_KEY = "engcrm_role";
const SESSION_KEY = "engcrm_session";

export async function getSession(): Promise<{ token: string | null; role: string | null; server: Server }> {
  const saved = await SecureStore.getItemAsync(SESSION_KEY);
  if (saved) {
    const session = JSON.parse(saved);
    if (typeof session.token !== "string" || typeof session.role !== "string" || !["production", "reviewer"].includes(session.server)) {
      throw new Error("Invalid stored session");
    }
    return { token: session.token, role: session.role, server: serverForSession(session.server) };
  }
  return { token: await SecureStore.getItemAsync(TOKEN_KEY), role: await SecureStore.getItemAsync(ROLE_KEY), server: "production" };
}

export async function getToken(): Promise<string | null> {
  return (await getSession()).token;
}

export async function getRole(): Promise<string | null> {
  return (await getSession()).role;
}

export async function saveToken(token: string, role: string, server: Server = "production"): Promise<void> {
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify({ token, role, server }));
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(ROLE_KEY);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(ROLE_KEY);
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await getToken();
  return token !== null;
}
