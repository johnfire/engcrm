// Which offer's pipeline a list shows: one offer's slug, or "all". Every list opens
// on all of them; picking an offer narrows this visit only. (Remembering the choice
// made an empty offer's pipeline look like a CRM with no data in it.)
import { useEffect, useState } from "react";

import { ALL_OFFERS, fetchOffers, Offer } from "../services/deals";

export function useOfferFilter() {
  const [offer, setOffer] = useState<string>(ALL_OFFERS);
  const [offers, setOffers] = useState<Offer[]>([]);

  useEffect(() => {
    fetchOffers()
      .then(setOffers)
      .catch(() => setOffers([])); // the list still loads; the picker offers only "All"
  }, []);

  return { offer, offers, choose: setOffer };
}
