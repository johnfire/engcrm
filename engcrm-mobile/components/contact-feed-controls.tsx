import { View } from "react-native";
import { ChipRow, FilterChip } from "./FilterChips";
import { useTranslation } from "../i18n/I18nContext";
import { ContactKind, ContactSort } from "../services/contact-feed";
import { PIPELINE_STAGES, stageLabelKey } from "../services/organizationState";

// The chip rows of the Contacts filter panel; the search box sits above, always on screen.
interface Props {
  kind: ContactKind | "";
  stage: string;
  sort: ContactSort;
  onKindChange: (kind: ContactKind | "") => void;
  onStageChange: (stage: string) => void;
  onSortChange: (sort: ContactSort) => void;
}

export function ContactFeedControls(props: Props) {
  const { t } = useTranslation();
  return (
    <View>
      <ChipRow label={t("contactFeed.kind")}>
        {(["", "person", "organization"] as const).map((choice) => <FilterChip key={choice || "all"}
          label={t(`contactFeed.${choice === "person" ? "standalone" : choice || "all"}`)} isActive={props.kind === choice} onPress={() => props.onKindChange(choice)} />)}
      </ChipRow>
      <ChipRow label={t("common.pipelineStage")}>
        {["", "none", ...PIPELINE_STAGES].map((choice) => <FilterChip key={choice || "all"}
          label={choice === "" ? t("contactFeed.allStages") : choice === "none" ? t("contactFeed.noStage") : t(stageLabelKey(choice))}
          isActive={props.stage === choice} onPress={() => props.onStageChange(choice)} />)}
      </ChipRow>
      <ChipRow label={t("contactFeed.sort")}>
        {(["last_contact", "name"] as const).map((choice) => <FilterChip key={choice} label={t(`contactFeed.${choice}`)}
          isActive={props.sort === choice} onPress={() => props.onSortChange(choice)} />)}
      </ChipRow>
    </View>
  );
}

