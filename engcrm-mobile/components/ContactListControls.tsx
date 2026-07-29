import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { ContactSortKey } from "../services/api";

const STATUS_FILTERS = [
  "",
  "cold",
  "contacted",
  "meeting",
  "proposal",
  "accepted",
  "rejected",
  "dropped",
];

const STATUS_LABEL_KEYS: Record<string, string> = {
  "": "contacts.statusAll",
  cold: "contacts.statusCold",
  contacted: "contacts.statusContacted",
  meeting: "contacts.statusMeeting",
  proposal: "contacts.statusProposal",
  accepted: "contacts.statusAccepted",
  rejected: "contacts.statusRejected",
  dropped: "contacts.statusDropped",
};

const PRIORITY_FILTERS = ["", "1", "2", "3", "4", "5", "unrated"];

const SORT_OPTIONS: {
  key: ContactSortKey;
  direction: "asc" | "desc";
  labelKey: string;
}[] = [
  { key: "created_at", direction: "desc", labelKey: "common.sortNewest" },
  { key: "name", direction: "asc", labelKey: "common.sortAZ" },
  { key: "type", direction: "asc", labelKey: "common.sortIndustry" },
  {
    key: "personal_priority",
    direction: "asc",
    labelKey: "contacts.sortPersonalPriority",
  },
];

interface Props {
  status: string;
  personalPriority: string;
  sort: ContactSortKey;
  direction: "asc" | "desc";
  onStatusChange: (status: string) => void;
  onPriorityChange: (priority: string) => void;
  onSortChange: (sort: ContactSortKey, direction: "asc" | "desc") => void;
}

function ChipRow({
  children,
  label,
}: {
  children: React.ReactNode;
  label?: string;
}) {
  return (
    <View>
      {label && <Text style={styles.label}>{label}</Text>}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filters}
        contentContainerStyle={styles.filtersContent}
      >
        {children}
      </ScrollView>
    </View>
  );
}

export function ContactListControls({
  status,
  personalPriority,
  sort,
  direction,
  onStatusChange,
  onPriorityChange,
  onSortChange,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      <ChipRow>
        {STATUS_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={t(STATUS_LABEL_KEYS[filter])}
            isActive={status === filter}
            onPress={() => onStatusChange(filter)}
          />
        ))}
      </ChipRow>
      <ChipRow label={t("personalPriority.title")}>
        {PRIORITY_FILTERS.map((filter) => (
          <FilterChip
            key={filter}
            label={
              filter === ""
                ? t("contacts.priorityAll")
                : filter === "unrated"
                  ? t("contacts.priorityUnrated")
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

function FilterChip({
  label,
  isActive,
  onPress,
}: {
  label: string;
  isActive: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={[styles.chip, isActive && styles.chipActive]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: isActive }}
    >
      <Text style={[styles.chipText, isActive && styles.chipTextActive]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  filters: { flexGrow: 0, marginBottom: 8, marginHorizontal: 16 },
  filtersContent: { alignItems: "center", gap: 8, paddingVertical: 6 },
  label: { color: "#666", fontSize: 11, marginHorizontal: 16 },
  chip: {
    backgroundColor: "#ffffff10",
    borderRadius: 16,
    justifyContent: "center",
    minHeight: 32,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  chipActive: { backgroundColor: "#7c6fff" },
  chipText: { color: "#888", fontSize: 12, fontWeight: "600", lineHeight: 16 },
  chipTextActive: { color: "#fff" },
});
