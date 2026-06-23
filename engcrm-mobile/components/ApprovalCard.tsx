import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  ScrollView,
} from "react-native";
import { Approval } from "../services/api";

interface Props {
  item: Approval;
  onApprove: (id: number) => void;
  onReject: (item: Approval) => void;
  onEdit: (item: Approval) => void;
}

export function ApprovalCard({ item, onApprove, onReject, onEdit }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <TouchableOpacity
        style={s.card}
        onPress={() => setExpanded(true)}
        activeOpacity={0.8}
      >
        <Text style={s.venue}>
          {item.name}, {item.city}
        </Text>
        <Text style={s.subject}>{item.draft_subject}</Text>
        <Text style={s.preview} numberOfLines={2}>
          {item.draft_body}
        </Text>
        <View style={s.actions}>
          <TouchableOpacity
            style={s.approveBtn}
            onPress={() => onApprove(item.id)}
          >
            <Text style={s.approveTxt}>Approve</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.rejectBtn} onPress={() => onReject(item)}>
            <Text style={s.rejectTxt}>Reject</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.editBtn} onPress={() => onEdit(item)}>
            <Text style={s.editTxt}>Edit</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>

      <Modal visible={expanded} animationType="slide">
        <View style={s.modal}>
          <Text style={s.modalTitle}>{item.draft_subject}</Text>
          <Text style={s.modalVenue}>
            {item.name} · {item.city}
          </Text>
          <ScrollView style={s.bodyScroll}>
            <Text style={s.bodyText}>{item.draft_body}</Text>
          </ScrollView>
          <TouchableOpacity
            style={s.closeBtn}
            onPress={() => setExpanded(false)}
          >
            <Text style={s.closeTxt}>Close</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  venue: { color: "#fff", fontSize: 14, fontWeight: "700", marginBottom: 4 },
  subject: { color: "#aaa", fontSize: 13, marginBottom: 6 },
  preview: { color: "#666", fontSize: 12, lineHeight: 18, marginBottom: 12 },
  actions: { flexDirection: "row", gap: 8 },
  approveBtn: {
    flex: 1,
    backgroundColor: "#22c55e20",
    borderRadius: 6,
    padding: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#22c55e50",
  },
  approveTxt: { color: "#22c55e", fontSize: 12, fontWeight: "600" },
  rejectBtn: {
    flex: 1,
    backgroundColor: "#ef444420",
    borderRadius: 6,
    padding: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ef444450",
  },
  rejectTxt: { color: "#ef4444", fontSize: 12, fontWeight: "600" },
  editBtn: {
    flex: 1,
    backgroundColor: "#ffffff10",
    borderRadius: 6,
    padding: 8,
    alignItems: "center",
  },
  editTxt: { color: "#aaa", fontSize: 12, fontWeight: "600" },
  modal: { flex: 1, backgroundColor: "#0f0f23", padding: 24, paddingTop: 60 },
  modalTitle: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 4,
  },
  modalVenue: { color: "#888", fontSize: 13, marginBottom: 20 },
  bodyScroll: { flex: 1 },
  bodyText: { color: "#ccc", fontSize: 15, lineHeight: 24 },
  closeBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
    marginTop: 16,
  },
  closeTxt: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
