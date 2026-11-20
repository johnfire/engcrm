import { View } from "react-native";
import { ChipRow, FilterChip } from "./FilterChips";
import { useTranslation } from "../i18n/I18nContext";
import { ContactKind } from "../services/contact-feed";
import { SortChips } from "./SortChips";
import { SortChoice, SortOption } from "../services/listSort";
import { CONTACT_SORTS, ContactSortKey } from "../services/listSortOptions";
import { PIPELINE_STAGES, stageLabelKey } from "../services/organizationState";

// The chip rows of the Contacts filter panel; the search box sits above, always on screen.
interface Props {
  kind: ContactKind | "";
  stage: string;
  sort: SortChoice<ContactSortKey>;
  onKindChange: (kind: ContactKind | "") => void;
  onStageChange: (stage: string) => void;
  onSortChange: (option: SortOption<ContactSortKey>) => void;
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
      <SortChips options={CONTACT_SORTS} sort={props.sort} onChoose={props.onSortChange} />
    </View>
  );
}

