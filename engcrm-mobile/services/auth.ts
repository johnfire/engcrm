import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "engcrm_jwt";
const ROLE_KEY = "engcrm_role";

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function getRole(): Promise<string | null> {
  return SecureStore.getItemAsync(ROLE_KEY);
}

export async function saveToken(token: string, role: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
  await SecureStore.setItemAsync(ROLE_KEY, role);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(ROLE_KEY);
}

export async function isLoggedIn(): Promise<boolean> {
  const token = await getToken();
  return token !== null;
}
