import { StyleSheet, TextInput, View } from "react-native";
import { ChipRow, FilterChip } from "./FilterChips";
import { useTranslation } from "../i18n/I18nContext";
import { ContactKind, ContactSort } from "../services/contact-feed";
import { PIPELINE_STAGES, stageLabelKey } from "../services/organizationState";

interface Props {
  search: string;
  kind: ContactKind | "";
  stage: string;
  sort: ContactSort;
  onSearchChange: (search: string) => void;
  onKindChange: (kind: ContactKind | "") => void;
  onStageChange: (stage: string) => void;
  onSortChange: (sort: ContactSort) => void;
  onSubmit: () => void;
}

export function ContactFeedControls(props: Props) {
  const { t } = useTranslation();
  return (
    <View>
      <TextInput style={styles.search} value={props.search} onChangeText={props.onSearchChange} onSubmitEditing={props.onSubmit}
        placeholder={t("contactFeed.search")} placeholderTextColor="#aaa" accessibilityLabel={t("contactFeed.search")}
        autoCapitalize="none" returnKeyType="search" />
      <ChipRow label={t("contactFeed.kind")}>
        {(["", "person", "organization"] as const).map((choice) => <FilterChip key={choice || "all"}
          label={t(`contactFeed.${choice || "all"}`)} isActive={props.kind === choice} onPress={() => props.onKindChange(choice)} />)}
      </ChipRow>
      <ChipRow label={t("common.pipelineStage")}>
        {["", "none", ...PIPELINE_STAGES].map((choice) => <FilterChip key={choice || "all"}
          label={choice === "" ? t("contactFeed.allStages") : choice === "none" ? t("contactFeed.noStage") : t(stageLabelKey(choice))}
          isActive={props.stage === choice} onPress={() => props.onStageChange(choice)} />)}
      </ChipRow>
      <ChipRow label={t("contactFeed.sort")}>
        {(["newest", "name"] as const).map((choice) => <FilterChip key={choice} label={t(`contactFeed.${choice}`)}
          isActive={props.sort === choice} onPress={() => props.onSortChange(choice)} />)}
      </ChipRow>
    </View>
  );
}

const styles = StyleSheet.create({
  search: { backgroundColor: "#1a1a2e", color: "#fff", borderRadius: 10, margin: 16, padding: 12, fontSize: 14 },
});
