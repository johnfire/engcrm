import { useLocalOffers } from "../hooks/useLocalOffers";
import { OfferFilterChips } from "./OfferFilterChips";

export function LocalOfferChips({ offer, onChange }: { offer: string; onChange(value: string): void }) {
  return <OfferFilterChips offer={offer} offers={useLocalOffers()} onChange={onChange} />;
}
