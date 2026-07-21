import { useEffect, useState } from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { isLoggedIn } from "../services/auth";
import { registerForPushNotifications } from "../services/notifications";

export default function RootLayout() {
  const router = useRouter();
  const segments = useSegments();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    isLoggedIn()
      .then((loggedIn) => {
        setChecked(true);
        const inDrawer = segments[0] === "(drawer)";
        if (!loggedIn && inDrawer) {
          router.replace("/login");
        } else if (loggedIn && !inDrawer) {
          router.replace("/(drawer)/contacts");
        }
      })
      .catch(() => {
        // Auth storage unreadable — fall through to login rather than hang
        // forever on the blank (!checked) screen.
        setChecked(true);
        if (segments[0] === "(drawer)") router.replace("/login");
      });
    // This is an initial-session gate; running again after a route change would
    // redirect the user away from their active screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Push registration is best-effort; never let it disrupt startup.
    if (checked) registerForPushNotifications();
  }, [checked]);

  if (!checked) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="forgot-password" />
      <Stack.Screen name="(drawer)" />
    </Stack>
  );
}
