import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

/** A name with its database id after it ("Acme Salon  #42"), muted, to tell
 * duplicates apart. The name stays its own text; the id sits beside it. */
export function NameWithId({ id, children }: { id: number; children: ReactNode }) {
  return (
    <View style={styles.row}>
      {children}
      <Text style={styles.id}>#{id}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "baseline", columnGap: 6, flexShrink: 1 },
  id: { color: "#888", fontWeight: "400", fontSize: 12 },
});
