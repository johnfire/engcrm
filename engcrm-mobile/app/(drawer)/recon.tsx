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
import { ReconContactCard } from "../../components/ReconContactCard";
import { useTranslation } from "../../i18n/I18nContext";

export default function ReconScreen() {
  const router = useRouter();
  const { t } = useTranslation();
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
        setError(t("recon.locationPermission"));
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      const { latitude, longitude } = position.coords;
      setItems(await fetchRecon(latitude, longitude, notContacted));
    } catch (caught: any) {
      setError(caught?.message || t("recon.couldntGetLocation"));
    } finally {
      setLoading(false);
    }
  }, [notContacted, t]);

  useFocusEffect(
    useCallback(() => {
      locate();
    }, [locate]),
  );

  function navigate(organization: ReconContact) {
    const url =
      organization.maps_uri ||
      `https://www.google.com/maps/search/?api=1&query=${organization.latitude},${organization.longitude}`;
    Linking.openURL(url);
  }

  function call(organization: ReconContact) {
    if (organization.phone) Linking.openURL(`tel:${organization.phone}`);
    else Alert.alert(t("recon.noPhoneTitle"), t("recon.noPhoneMessage"));
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" size="large" />
        <Text style={styles.locating}>{t("recon.locating")}</Text>
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
            {t("recon.notContactedOnly")}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={locate} style={styles.relocate}>
          <Text style={styles.relocateText}>{t("recon.relocate")}</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={items}
        keyExtractor={(organization) => String(organization.id)}
        renderItem={({ item }) => <ReconContactCard organization={item} onCall={() => call(item)} onNavigate={() => navigate(item)} onScan={() => router.push("/(drawer)/capture")} />}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={locate} tintColor="#7c6fff" />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>{error ? error : t("recon.empty")}</Text>
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
  empty: { color: "#777", textAlign: "center", marginTop: 60, fontSize: 14, lineHeight: 22 },
});
