// The offer picker above a list: every offer at once, or one offer's pipeline.
import { useTranslation } from "../i18n/I18nContext";
import { ALL_OFFERS, Offer } from "../services/deals";
import { ChipRow, FilterChip } from "./FilterChips";

export function OfferFilterChips({ offer, offers, onChange }: {
  offer: string;
  offers: Offer[];
  onChange: (offer: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ChipRow label={t("offerFilter.label")}>
      <FilterChip label={t("offerFilter.all")} isActive={offer === ALL_OFFERS} onPress={() => onChange(ALL_OFFERS)} />
      {offers.map((o) => (
        <FilterChip key={o.slug} label={o.name} isActive={offer === o.slug} onPress={() => onChange(o.slug)} />
      ))}
    </ChipRow>
  );
}
