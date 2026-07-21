import { Modal, View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { useTranslation } from "../i18n/I18nContext";

const CLASSIFICATIONS = [
  { key: "interested", labelKey: "classifySheet.interested", color: "#22c55e" },
  { key: "warm", labelKey: "classifySheet.warm", color: "#84cc16" },
  { key: "not_interested", labelKey: "classifySheet.notInterested", color: "#ef4444" },
  { key: "not_possible", labelKey: "classifySheet.notPossible", color: "#f97316" },
  { key: "opt_out", labelKey: "classifySheet.optOut", color: "#dc2626" },
  { key: "bounce", labelKey: "classifySheet.bounce", color: "#888" },
  { key: "other", labelKey: "classifySheet.other", color: "#888" },
];

interface Props {
  visible: boolean;
  onSelect: (classification: string) => void;
  onCancel: () => void;
}

export function ClassifySheet({ visible, onSelect, onCancel }: Props) {
  const { t } = useTranslation();
  return (
    <Modal visible={visible} transparent animationType="slide">
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <Text style={styles.title}>{t("classifySheet.title")}</Text>
          {CLASSIFICATIONS.map((classification) => (
            <TouchableOpacity
              key={classification.key}
              style={styles.option}
              onPress={() => onSelect(classification.key)}
            >
              <Text style={[styles.optionText, { color: classification.color }]}>
                {t(classification.labelKey)}
              </Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
            <Text style={styles.cancelText}>{t("classifySheet.cancel")}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
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
