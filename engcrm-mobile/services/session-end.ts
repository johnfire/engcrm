// One way to end a session, and the rule for what survives the next sign-in.
//
// Signing out stops field mode first (it uploads under the login, and its foreground
// service would otherwise keep recording after the token is gone), then clears the token.
// Queued captures, recorded points and unsent drafts stay on the phone for the SAME
// account, because a photo taken offline must never be lost. They are removed when a
// DIFFERENT account signs in, so one person's data is never uploaded or shown under
// another's login on a shared phone.
import * as SecureStore from "expo-secure-store";

import { clearToken } from "./auth";
import { clearCardQueue } from "./cardQueue";
import { clearAllDrafts } from "./drafts";
import { clearFieldData, stopFieldMode } from "./fieldMode";

const LAST_ACCOUNT_KEY = "engcrm_last_account";

/** Every sign-out and every dead-token bounce goes through here. */
export async function endSession(): Promise<void> {
  await stopFieldMode().catch(() => undefined); // sends what was recorded, while the token still works
  await clearToken();
}

/** Remove everything captured on this phone that has not reached the server. */
async function purgeLocalCaptures(): Promise<void> {
  await Promise.all([clearFieldData(), clearCardQueue(), clearAllDrafts()].map((step) => step.catch(() => undefined)));
}

/** Call after a successful login, before the new session is saved. */
export async function recordSignIn(email: string): Promise<void> {
  const account = email.trim().toLowerCase();
  const previous = await SecureStore.getItemAsync(LAST_ACCOUNT_KEY).catch(() => null);
  if (previous && previous !== account) await purgeLocalCaptures();
  await SecureStore.setItemAsync(LAST_ACCOUNT_KEY, account);
}
