// Which offer a new organization or person goes into: the one used last on this
// phone, else Consulting. `remember` keeps the choice for next time.
import { useEffect, useState } from "react";

import { fetchOffers, getLastOffer, Offer, setLastOffer } from "../services/deals";

export function useCreationOffer() {
  const [offer, setOffer] = useState("consulting");
  const [offers, setOffers] = useState<Offer[]>([]);

  useEffect(() => {
    getLastOffer().then(setOffer);
    fetchOffers()
      .then(setOffers)
      .catch(() => setOffers([])); // offline: no picker, the server enters it into Consulting
  }, []);

  // A remembered offer that was archived since falls back to Consulting.
  const chosen = offers.length && !offers.some((o) => o.slug === offer) ? "consulting" : offer;
  return {
    offer: chosen,
    offers,
    choose: setOffer,
    remember: () => setLastOffer(chosen),
    /** What to send: nothing when the offers could not be read. */
    sent: offers.length ? chosen : undefined,
  };
}
