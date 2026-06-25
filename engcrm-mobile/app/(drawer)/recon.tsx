import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
  Linking,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import * as Location from "expo-location";
import { fetchRecon, ReconContact } from "../../services/api";

function formatDistance(meters: number): string {
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

export default function ReconScreen() {
  const router = useRouter();
  const [items, setItems] = useState<ReconContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notContacted, setNotContacted] = useState(true);

  const locate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setError("Location permission is needed to find nearby leads.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      const { latitude, longitude } = position.coords;
      setItems(await fetchRecon(latitude, longitude, notContacted));
    } catch (caught: any) {
      setError(caught?.message || "Couldn't get your location. Try again.");
    } finally {
      setLoading(false);
    }
  }, [notContacted]);

  useFocusEffect(
    useCallback(() => {
      locate();
    }, [locate]),
  );

  function navigate(contact: ReconContact) {
    const url =
      contact.maps_uri ||
      `https://www.google.com/maps/search/?api=1&query=${contact.latitude},${contact.longitude}`;
    Linking.openURL(url);
  }

  function call(contact: ReconContact) {
    if (contact.phone) Linking.openURL(`tel:${contact.phone}`);
    else Alert.alert("No phone", "No phone number on file for this lead.");
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" size="large" />
        <Text style={styles.locating}>Finding leads near you…</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.toolbar}>
        <TouchableOpacity
          style={[styles.toggle, notContacted && styles.toggleOn]}
          onPress={() => setNotContacted((value) => !value)}
        >
          <Text style={[styles.toggleText, notContacted && styles.toggleTextOn]}>
            Not contacted only
          </Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={locate} style={styles.relocate}>
          <Text style={styles.relocateText}>↻ Re-locate</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={items}
        keyExtractor={(contact) => String(contact.id)}
        renderItem={({ item }) => {
          const meta = [item.type, item.city].filter(Boolean).join(" · ");
          return (
            <View style={styles.row}>
              <View style={styles.rowHead}>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.distance}>{formatDistance(item.distance_m)}</Text>
              </View>
              <View style={styles.metaRow}>
                {!!meta && <Text style={styles.meta}>{meta}</Text>}
                {item.rating != null && <Text style={styles.rating}>★ {item.rating}</Text>}
                {item.fit_score != null && <Text style={styles.fit}>fit {item.fit_score}</Text>}
                {!!item.status && <Text style={styles.status}>{item.status}</Text>}
              </View>
              <View style={styles.actions}>
                <TouchableOpacity style={styles.action} onPress={() => call(item)}>
                  <Text style={styles.actionText}>Call</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.action} onPress={() => navigate(item)}>
                  <Text style={styles.actionText}>Navigate</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.action}
                  onPress={() => router.push("/(drawer)/capture")}
                >
                  <Text style={styles.actionText}>Scan card</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        }}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={locate} tintColor="#7c6fff" />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {error
              ? error
              : "No leads with coordinates near you. Scan some cities first."}
          </Text>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  center: {
    flex: 1,
    backgroundColor: "#0f0f23",
    justifyContent: "center",
    alignItems: "center",
    gap: 14,
  },
  locating: { color: "#888", fontSize: 14 },
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  toggle: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 16,
    backgroundColor: "#ffffff10",
  },
  toggleOn: { backgroundColor: "#7c6fff" },
  toggleText: { color: "#888", fontSize: 13, fontWeight: "600" },
  toggleTextOn: { color: "#fff" },
  relocate: { paddingHorizontal: 10, paddingVertical: 7 },
  relocateText: { color: "#7c6fff", fontSize: 13, fontWeight: "600" },
  list: { padding: 16, paddingTop: 4 },
  row: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#ffffff12",
  },
  rowHead: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  name: { color: "#fff", fontSize: 16, fontWeight: "600", flex: 1 },
  distance: { color: "#b9adff", fontSize: 13, fontWeight: "600" },
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 5,
    flexWrap: "wrap",
  },
  meta: { color: "#888", fontSize: 12 },
  rating: { color: "#f0c040", fontSize: 12 },
  fit: {
    color: "#aaa",
    fontSize: 12,
    backgroundColor: "#ffffff10",
    paddingHorizontal: 7,
    borderRadius: 10,
  },
  status: { color: "#777", fontSize: 12 },
  actions: { flexDirection: "row", gap: 8, marginTop: 12 },
  action: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#7c6fff55",
  },
  actionText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  empty: { color: "#777", textAlign: "center", marginTop: 60, fontSize: 14, lineHeight: 22 },
});
