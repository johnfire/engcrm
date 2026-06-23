import { useEffect, useState } from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { isLoggedIn } from "../services/auth";
import { registerForPushNotifications } from "../services/notifications";

export default function RootLayout() {
  const router = useRouter();
  const segments = useSegments();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    isLoggedIn().then((loggedIn) => {
      setChecked(true);
      const inDrawer = segments[0] === "(drawer)";
      if (!loggedIn && inDrawer) {
        router.replace("/login");
      } else if (loggedIn && !inDrawer) {
        router.replace("/(drawer)/approvals");
      }
    });
  }, []);

  useEffect(() => {
    if (checked) registerForPushNotifications();
  }, [checked]);

  if (!checked) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="(drawer)" />
    </Stack>
  );
}
