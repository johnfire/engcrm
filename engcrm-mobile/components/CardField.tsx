import { View, Text, TextInput, StyleSheet } from "react-native";

/**
 * One labelled text field on the card-confirm form. Extracted from
 * card-confirm.tsx so that screen stays within the component size limit.
 */
export function CardField({
  label,
  value,
  onChange,
  keyboardType,
  multiline,
}: {
  label: string;
  value?: string | null;
  onChange: (value: string) => void;
  keyboardType?: "default" | "email-address" | "phone-pad" | "url";
  multiline?: boolean;
}) {
  const noCaps = keyboardType === "email-address" || keyboardType === "url";
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, multiline && styles.inputMultiline]}
        value={value ?? ""}
        onChangeText={onChange}
        placeholderTextColor="#555"
        autoCapitalize={noCaps ? "none" : "sentences"}
        autoCorrect={false}
        keyboardType={keyboardType ?? "default"}
        multiline={multiline}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  field: { marginBottom: 12 },
  label: { color: "#888", fontSize: 12, marginBottom: 4, marginLeft: 2 },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 15,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  inputMultiline: { minHeight: 70, textAlignVertical: "top" },
});
