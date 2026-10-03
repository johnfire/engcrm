import { ReactNode } from "react";
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

export function ChipRow({
  children,
  label,
}: {
  children: ReactNode;
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

export function FilterChip({
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
