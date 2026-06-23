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
  const [reason, setReason] = useState("");

  function handleConfirm() {
    onConfirm(reason.trim());
    setReason("");
  }

  return (
    <Modal visible={visible} transparent animationType="slide">
      <KeyboardAvoidingView
        style={s.overlay}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={s.sheet}>
          <Text style={s.title}>Reject draft</Text>
          <Text style={s.subtitle}>{venueName}</Text>
          <Text style={s.label}>Reason (optional)</Text>
          <TextInput
            style={s.input}
            placeholder="e.g. Too formal, needs warmer tone"
            placeholderTextColor="#555"
            value={reason}
            onChangeText={setReason}
            multiline
            autoFocus
          />
          <View style={s.row}>
            <TouchableOpacity style={s.cancelBtn} onPress={onCancel}>
              <Text style={s.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.confirmBtn} onPress={handleConfirm}>
              <Text style={s.confirmText}>Confirm Reject</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
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
