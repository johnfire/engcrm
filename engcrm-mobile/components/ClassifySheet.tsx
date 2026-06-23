import { Modal, View, Text, TouchableOpacity, StyleSheet } from "react-native";

const CLASSIFICATIONS = [
  { key: "interested", label: "Interested", color: "#22c55e" },
  { key: "warm", label: "Warm / Considering", color: "#84cc16" },
  { key: "not_interested", label: "Not Interested", color: "#ef4444" },
  { key: "not_possible", label: "Not Possible", color: "#f97316" },
  { key: "opt_out", label: "Opt Out", color: "#dc2626" },
  { key: "bounce", label: "Bounce", color: "#888" },
  { key: "other", label: "Other", color: "#888" },
];

interface Props {
  visible: boolean;
  onSelect: (classification: string) => void;
  onCancel: () => void;
}

export function ClassifySheet({ visible, onSelect, onCancel }: Props) {
  return (
    <Modal visible={visible} transparent animationType="slide">
      <View style={s.overlay}>
        <View style={s.sheet}>
          <Text style={s.title}>Classify reply</Text>
          {CLASSIFICATIONS.map((c) => (
            <TouchableOpacity
              key={c.key}
              style={s.option}
              onPress={() => onSelect(c.key)}
            >
              <Text style={[s.optionText, { color: c.color }]}>{c.label}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={s.cancelBtn} onPress={onCancel}>
            <Text style={s.cancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "#00000088",
  },
  sheet: {
    backgroundColor: "#1e1e3a",
    borderRadius: 16,
    padding: 20,
    margin: 8,
  },
  title: { color: "#fff", fontSize: 16, fontWeight: "700", marginBottom: 16 },
  option: { padding: 14, borderBottomWidth: 1, borderBottomColor: "#ffffff10" },
  optionText: { fontSize: 15, fontWeight: "600" },
  cancelBtn: {
    marginTop: 12,
    padding: 14,
    alignItems: "center",
    backgroundColor: "#ffffff10",
    borderRadius: 8,
  },
  cancelText: { color: "#aaa", fontSize: 15, fontWeight: "600" },
});
