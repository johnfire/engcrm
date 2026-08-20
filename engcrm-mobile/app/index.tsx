import { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import { isLoggedIn } from "../services/auth";

/**
 * Root route ("/"). Without this, launching the app (engcrm:///) matches no
 * route and shows expo-router's "Unmatched Route" screen. Redirect to the
 * drawer when signed in, otherwise to login.
 */
export default function Index() {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    isLoggedIn().then((ok) => setTarget(ok ? "/(drawer)/organizations" : "/login"));
  }, []);

  if (!target) return null;
  return <Redirect href={target} />;
}
