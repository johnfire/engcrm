import { useTranslation } from "../i18n/I18nContext";
import type { SortChoice, SortOption } from "../services/listSort";
import { PERSON_SORTS, type PersonSortKey } from "../services/listSortOptions";
import { PIPELINE_STAGES, stageLabelKey } from "../services/organizationState";
import { ChipRow, FilterChip } from "./FilterChips";
import { SortChips } from "./SortChips";

export const RATING_LABELS = ["contactValue.exceptional", "contactValue.high", "contactValue.medium",
  "contactValue.low", "contactValue.minimal"];
const STAGES = ["", "none", ...PIPELINE_STAGES];
const RATINGS = ["", "1", "2+", "3+", "unrated"];

interface Props {
  stage: string; rating: string; linkedin: string; sort: SortChoice<PersonSortKey>;
  onStageChange(value: string): void; onRatingChange(value: string): void; onLinkedinChange(value: string): void;
  onSortChange(option: SortOption<PersonSortKey>): void;
}

export function PeopleListControls(props: Props) {
  const { t } = useTranslation();
  function ratingLabel(value: string): string {
    if (!value) return t("people.anyRating");
    if (value === "unrated") return t("people.unrated");
    const number = Number(value[0]);
    const label = t(RATING_LABELS[number - 1]);
    return value.endsWith("+") ? `${number} ${t("people.ratingOrBetter", { label })}` : `${number} ${label}`;
  }
  return <>
    <ChipRow label={t("common.pipelineStage")}>
      {STAGES.map((value) => <FilterChip key={value} label={!value ? t("organizations.allStages") :
        value === "none" ? t("people.noStage") : t(stageLabelKey(value))} isActive={props.stage === value} onPress={() => props.onStageChange(value)} />)}
    </ChipRow>
    <ChipRow label={t("people.ratingFilter")}>
      {RATINGS.map((value) => <FilterChip key={value || "any"} label={ratingLabel(value)} isActive={props.rating === value}
        onPress={() => props.onRatingChange(value)} />)}
    </ChipRow>
    <ChipRow label={t("people.linkedinFilter")}>
      <FilterChip label={t("people.everyone")} isActive={props.linkedin === ""} onPress={() => props.onLinkedinChange("")} />
      <FilterChip label={t("people.linkedinOnly")} isActive={props.linkedin === "1"} onPress={() => props.onLinkedinChange("1")} />
      <FilterChip label={t("people.linkedinUnlinked")} isActive={props.linkedin === "unlinked"} onPress={() => props.onLinkedinChange("unlinked")} />
    </ChipRow>
    <SortChips options={PERSON_SORTS} sort={props.sort} onChoose={props.onSortChange} />
  </>;
}
