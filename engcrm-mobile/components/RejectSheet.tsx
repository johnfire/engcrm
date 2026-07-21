import { useState } from "react";
import {
  Modal,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useTranslation } from "../i18n/I18nContext";

interface Props {
  visible: boolean;
  venueName: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

export function RejectSheet({
  visible,
  venueName,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");

  function handleConfirm() {
    onConfirm(reason.trim());
    setReason("");
  }

  return (
    <Modal visible={visible} transparent animationType="slide">
      <KeyboardAvoidingView
        style={styles.overlay}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.sheet}>
          <Text style={styles.title}>{t("rejectSheet.title")}</Text>
          <Text style={styles.subtitle}>{venueName}</Text>
          <Text style={styles.label}>{t("rejectSheet.reasonLabel")}</Text>
          <TextInput
            style={styles.input}
            placeholder={t("rejectSheet.reasonPlaceholder")}
            placeholderTextColor="#555"
            value={reason}
            onChangeText={setReason}
            multiline
            autoFocus
          />
          <View style={styles.row}>
            <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
              <Text style={styles.cancelText}>{t("rejectSheet.cancel")}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.confirmBtn} onPress={handleConfirm}>
              <Text style={styles.confirmText}>{t("rejectSheet.confirmReject")}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
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
  title: { color: "#fff", fontSize: 16, fontWeight: "700", marginBottom: 4 },
  subtitle: { color: "#888", fontSize: 13, marginBottom: 16 },
  label: { color: "#888", fontSize: 12, marginBottom: 6 },
  input: {
    backgroundColor: "#ffffff10",
    color: "#fff",
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 80,
    marginBottom: 16,
  },
  row: { flexDirection: "row", gap: 10 },
  cancelBtn: {
    flex: 1,
    backgroundColor: "#ffffff10",
    borderRadius: 8,
    padding: 12,
    alignItems: "center",
  },
  cancelText: { color: "#aaa", fontWeight: "600" },
  confirmBtn: {
    flex: 1,
    backgroundColor: "#ef4444",
    borderRadius: 8,
    padding: 12,
    alignItems: "center",
  },
  confirmText: { color: "#fff", fontWeight: "700" },
});
