import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";

import { readLocalWorkspace } from "../services/local-records";
import { useOffline } from "../services/offline-context";

type Snapshot = Awaited<ReturnType<typeof readLocalWorkspace>>;

export function useLocalSnapshot(): { snapshot: Snapshot | null; error: boolean } {
  const { session, status } = useOffline();
  const [loaded, setLoaded] = useState<{ database: object; snapshot: Snapshot } | null>(null);
  const [failed, setFailed] = useState<object | null>(null);
  const snapshot = session && loaded?.database === session.database ? loaded.snapshot : null;
  useFocusEffect(useCallback(() => {
    let active = true;
    if (session && status?.ready) {
      readLocalWorkspace(session.database).then((value) => {
        if (active) { setLoaded({ database: session.database, snapshot: value }); setFailed(null); }
      }).catch(() => { if (active) setFailed(session.database); });
    }
    return () => { active = false; };
  }, [session, status]));
  return { snapshot, error: !!session && failed === session.database };
}
