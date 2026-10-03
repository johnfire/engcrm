import { useTranslation } from "../i18n/I18nContext";
import { ChipRow, FilterChip } from "./FilterChips";
import { OrganizationSortKey } from "../services/api";
import {
  PIPELINE_STAGES,
  STATUSES,
  SUPPRESSION_FLAGS,
  flagLabelKey,
  stageLabelKey,
  statusLabelKey,
} from "../services/organizationState";

// "" is the "all" chip; the rest come from the shared vocabulary, so a value
// added in gcrm/contact_state.py shows up here without editing this file.
const STAGE_FILTERS = ["", ...PIPELINE_STAGES];
const STATUS_FILTERS = ["", ...STATUSES];
const FLAG_FILTERS = ["", ...SUPPRESSION_FLAGS];

const PRIORITY_FILTERS = ["", "1", "2", "3", "4", "5", "unrated"];

const SORT_OPTIONS: {
  key: OrganizationSortKey;
  direction: "asc" | "desc";
  labelKey: string;
}[] = [
  { key: "created_at", direction: "desc", labelKey: "common.sortNewest" },
  { key: "name", direction: "asc", labelKey: "common.sortAZ" },
  { key: "type", direction: "asc", labelKey: "common.sortIndustry" },
  {
    key: "personal_priority",
    direction: "asc",
    labelKey: "organizations.sortPersonalPriority",
  },
];

interface Props {
  stage: string;
  status: string;
  personalPriority: string;
  linkedin: string; // "" = any, "1" = I know someone there
  suppressed: string; // "" = any, or one suppression flag
  sort: OrganizationSortKey;
  direction: "asc" | "desc";
  onStageChange: (stage: string) => void;
  onStatusChange: (status: string) => void;
  onPriorityChange: (priority: string) => void;
  onLinkedinChange: (linkedin: string) => void;
  onSuppressedChange: (suppressed: string) => void;
  onSortChange: (sort: OrganizationSortKey, direction: "asc" | "desc") => void;
}

export function OrganizationListControls({
  stage,
  status,
  personalPriority,
  linkedin,
  suppressed,
  sort,
  direction,
  onStageChange,
  onStatusChange,
  onPriorityChange,
  onLinkedinChange,
  onSuppressedChange,
  onSortChange,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      <ChipRow label={t("common.pipelineStage")}>
        {STAGE_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={filter === "" ? t("organizations.allStages") : t(stageLabelKey(filter))}
            isActive={stage === filter}
            onPress={() => onStageChange(filter)}
          />
        ))}
      </ChipRow>
      <ChipRow label={t("common.status")}>
        {STATUS_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={filter === "" ? t("organizations.statusAll") : t(statusLabelKey(filter))}
            isActive={status === filter}
            onPress={() => onStatusChange(filter)}
          />
        ))}
      </ChipRow>
      <ChipRow label={t("organizations.linkedinFilter")}>
        <FilterChip
          label={t("organizations.linkedinAny")}
          isActive={linkedin === ""}
          onPress={() => onLinkedinChange("")}
        />
        <FilterChip
          label={t("organizations.linkedinKnow")}
          isActive={linkedin === "1"}
          onPress={() => onLinkedinChange("1")}
        />
      </ChipRow>
      <ChipRow label={t("organizations.flagFilter")}>
        {FLAG_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={filter === "" ? t("organizations.statusAll") : t(flagLabelKey(filter))}
            isActive={suppressed === filter}
            onPress={() => onSuppressedChange(filter)}
          />
        ))}
      </ChipRow>
      <ChipRow label={t("personalPriority.title")}>
        {PRIORITY_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={
              filter === ""
                ? t("organizations.priorityAll")
                : filter === "unrated"
                  ? t("organizations.priorityUnrated")
                  : `P${filter}`
            }
            isActive={personalPriority === filter}
            onPress={() => onPriorityChange(filter)}
          />
        ))}
      </ChipRow>
      <ChipRow label={t("common.sortBy")}>
        {SORT_OPTIONS.map((option) => (
          <FilterChip
            key={option.key}
            label={t(option.labelKey)}
            isActive={sort === option.key && direction === option.direction}
            onPress={() => onSortChange(option.key, option.direction)}
          />
        ))}
      </ChipRow>
    </>
  );
}
