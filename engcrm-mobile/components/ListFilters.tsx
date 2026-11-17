// The top of a phone list: a search box and a Filters button that are always on
// screen, and the filter rows folded away beneath them until asked for, so the
// list itself gets the screen. The button counts the filters in use, so a
// narrowed list is never mistaken for everything.
import type { ReactNode } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";

export function ListSearchRow({ placeholder, search, onSearchChange, onSubmit, filtersOpen, activeFilters, onToggleFilters, action }: {
  placeholder: string;
  search: string;
  onSearchChange: (search: string) => void;
  onSubmit: () => void;
  filtersOpen: boolean;
  activeFilters: number;
  onToggleFilters: () => void;
  action?: ReactNode; // e.g. the Add button, kept beside the search
}) {
  const { t } = useTranslation();
  const label = activeFilters > 0 ? t("listFilters.buttonActive", { count: activeFilters }) : t("listFilters.button");
  return (
    <View style={styles.row}>
      <TextInput style={styles.search} placeholder={placeholder} placeholderTextColor="#555" value={search}
        onChangeText={onSearchChange} onSubmitEditing={onSubmit} returnKeyType="search" autoCapitalize="none"
        accessibilityLabel={placeholder} />
      <TouchableOpacity style={[styles.toggle, activeFilters > 0 && styles.toggleActive]} onPress={onToggleFilters}
        accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ expanded: filtersOpen }}>
        <Text style={styles.toggleText}>{`${label} ${filtersOpen ? "▴" : "▾"}`}</Text>
      </TouchableOpacity>
      {action}
    </View>
  );
}

export function FilterPanel({ open, activeFilters, onClear, children }: {
  open: boolean;
  activeFilters: number;
  onClear: () => void; // puts every filter back to "all"; search and sort stay
  children: ReactNode;
}) {
  const { t } = useTranslation();
  if (!open) return null;
  return (
    <View style={styles.panel}>
      {activeFilters > 0 && (
        <TouchableOpacity style={styles.clear} onPress={onClear} accessibilityRole="button">
          <Text style={styles.clearText}>{t("listFilters.clear")}</Text>
        </TouchableOpacity>
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: "center", flexDirection: "row", gap: 8, margin: 16, marginBottom: 8 },
  search: { backgroundColor: "#1a1a2e", borderRadius: 10, color: "#fff", flex: 1, fontSize: 14, padding: 12 },
  toggle: { alignItems: "center", backgroundColor: "#1a1a2e", borderColor: "#ffffff20", borderRadius: 10,
    borderWidth: 1, justifyContent: "center", minHeight: 44, paddingHorizontal: 12 },
  toggleActive: { borderColor: "#7c6fff" },
  toggleText: { color: "#fff", fontSize: 14, fontWeight: "600" },
  panel: { borderBottomColor: "#ffffff12", borderBottomWidth: 1, paddingBottom: 4 },
  clear: { alignSelf: "flex-end", justifyContent: "center", marginHorizontal: 16, minHeight: 36, paddingHorizontal: 8 },
  clearText: { color: "#b9adff", fontSize: 13, fontWeight: "600" },
});
