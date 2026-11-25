import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";

import type { Offer } from "../services/deals";
import { readLocalOffers } from "../services/local-offers";
import { useOffline } from "../services/offline-context";

export function useLocalOffers(): Offer[] {
  const { session, status } = useOffline();
  const [loaded, setLoaded] = useState<{ database: object; offers: Offer[] } | null>(null);
  useFocusEffect(useCallback(() => {
    let active = true;
    if (session && status?.ready) readLocalOffers(session.database)
      .then((offers) => { if (active) setLoaded({ database: session.database, offers }); })
      .catch(() => { if (active) setLoaded(null); });
    return () => { active = false; };
  }, [session, status]));
  return session && loaded?.database === session.database ? loaded.offers : [];
}
