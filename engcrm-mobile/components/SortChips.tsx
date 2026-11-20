import { useTranslation } from "../i18n/I18nContext";
import { ChipRow, FilterChip } from "./FilterChips";
import { SortChoice, SortOption } from "../services/listSort";

/** The "Sort by" chip row. The active chip shows its direction; tapping it reverses it. */
export function SortChips<Key extends string>({
  options,
  sort,
  onChoose,
}: {
  options: readonly SortOption<Key>[];
  sort: SortChoice<Key>;
  onChoose: (option: SortOption<Key>) => void;
}) {
  const { t } = useTranslation();
  return (
    <ChipRow label={t("common.sortBy")}>
      {options.map((option) => {
        const isActive = sort.key === option.key;
        const arrow = isActive ? (sort.direction === "asc" ? " ↑" : " ↓") : "";
        return (
          <FilterChip
            key={option.key}
            label={t(option.labelKey) + arrow}
            isActive={isActive}
            onPress={() => onChoose(option)}
          />
        );
      })}
    </ChipRow>
  );
}
