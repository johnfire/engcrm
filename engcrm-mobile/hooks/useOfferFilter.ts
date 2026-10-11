// Which offer's pipeline a list shows, remembered on the phone: one offer's slug,
// or "all". `offer` is null until the remembered choice has been read, so a list
// can wait for it instead of loading the wrong pipeline first.
import { useEffect, useState } from "react";

import { ALL_OFFERS, fetchOffers, getOfferFilter, Offer, setOfferFilter } from "../services/deals";

export function useOfferFilter() {
  const [offer, setOffer] = useState<string | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);

  useEffect(() => {
    getOfferFilter().then(setOffer);
    fetchOffers()
      .then(setOffers)
      .catch(() => setOffers([])); // the list still loads; the picker offers only "All"
  }, []);

  function choose(next: string) {
    setOffer(next);
    void setOfferFilter(next);
  }

  // A remembered offer that no longer exists (archived) falls back to all of them.
  const known = offer === null || offer === ALL_OFFERS || offers.length === 0 || offers.some((o) => o.slug === offer);
  return { offer: known ? offer : ALL_OFFERS, offers, choose };
}
