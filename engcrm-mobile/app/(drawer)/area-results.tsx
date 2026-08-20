import { useCallback, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, Platform } from "react-native";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { AppleMaps, GoogleMaps } from "expo-maps";
import { AreaOrganization, fetchAreaOrganizations } from "../../services/api";
import { useTranslation } from "../../i18n/I18nContext";

export default function AreaResultsScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { areaId } = useLocalSearchParams<{ areaId: string }>();

  const [organizations, setOrganizations] = useState<AreaOrganization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOrganizations(await fetchAreaOrganizations(Number(areaId)));
    } catch (caught: any) {
      setError(caught?.message || t("common.tryAgain"));
    } finally {
      setLoading(false);
    }
  }, [areaId, t]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  if (!organizations.length) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>{t("areaResults.empty")}</Text>
      </View>
    );
  }

  const markers = organizations.map((organization) => ({
    id: String(organization.id),
    coordinates: { latitude: organization.latitude, longitude: organization.longitude },
    title: organization.name,
    snippet: `${organization.type || ""} · ${organization.pipeline_stage}`.trim(),
  }));
  const first = organizations[0];
  const cameraPosition = {
    coordinates: { latitude: first.latitude, longitude: first.longitude },
    zoom: 15,
  };

  function onMarkerClick(marker: { id?: string | null }) {
    if (marker.id) {
      router.push({ pathname: "/(drawer)/organization-detail", params: { id: marker.id } });
    }
  }

  return (
    <View style={styles.container}>
      {Platform.OS === "ios" ? (
        <AppleMaps.View
          style={styles.map}
          cameraPosition={cameraPosition}
          markers={markers}
          onMarkerClick={onMarkerClick}
        />
      ) : (
        <GoogleMaps.View
          style={styles.map}
          cameraPosition={cameraPosition}
          markers={markers}
          onMarkerClick={onMarkerClick}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  map: { flex: 1 },
  center: { flex: 1, backgroundColor: "#0f0f23", justifyContent: "center", alignItems: "center", padding: 24 },
  errorText: { color: "#ef8a8a", fontSize: 14, textAlign: "center" },
  emptyText: { color: "#888", fontSize: 14, textAlign: "center" },
});
