import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { completeHelpTour, fetchHelp, HelpArticle, sendHelpFeedback } from "../../services/api";
import { useTranslation } from "../../i18n/I18nContext";

const TOUR_KEYS = ["help.tourContacts", "help.tourResearch", "help.tourApprovals", "help.tourCapture"];

export default function HelpScreen() {
  const { t } = useTranslation();
  const { tour } = useLocalSearchParams<{ tour?: string }>();
  const [articles, setArticles] = useState<HelpArticle[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<HelpArticle | null>(null);
  const [tourVisible, setTourVisible] = useState(false);
  const [tourStep, setTourStep] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try { setArticles(await fetchHelp(query)); }
    catch { Alert.alert(t("help.loadFailedTitle"), t("help.loadFailedMessage")); }
    finally { setLoading(false); }
  }, [query, t]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // The root session gate uses this route parameter for a first-time customer.
  // It remains restartable from the button for people who skipped it earlier.
  useFocusEffect(useCallback(() => {
    if (tour === "1") setTourVisible(true);
  }, [tour]));

  async function finishTour() {
    try { await completeHelpTour(); }
    catch { /* Tour remains useful even if the best-effort persistence call fails. */ }
    setTourVisible(false);
  }

  async function rateArticle(article: HelpArticle, helpful: boolean) {
    try {
      await sendHelpFeedback(article.id, helpful);
      Alert.alert(t("help.thanksTitle"), t("help.thanksMessage"));
    } catch { Alert.alert(t("help.feedbackFailedTitle"), t("help.feedbackFailedMessage")); }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.intro}>{t("help.intro")}</Text>
      <TouchableOpacity style={styles.tourButton} onPress={() => { setTourStep(0); setTourVisible(true); }} accessibilityRole="button" accessibilityLabel={t("help.startTour")}>
        <Text style={styles.tourText}>{t("help.startTour")}</Text>
      </TouchableOpacity>
      <TextInput value={query} onChangeText={setQuery} onSubmitEditing={load} placeholder={t("help.searchPlaceholder")} placeholderTextColor="#888" style={styles.search} accessibilityLabel={t("help.searchPlaceholder")} returnKeyType="search" />
      {loading ? <ActivityIndicator color="#7c6fff" style={styles.loading} /> : <FlatList data={articles} keyExtractor={(article) => String(article.id)} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor="#7c6fff" />} renderItem={({ item }) => <TouchableOpacity style={styles.article} onPress={() => setSelected(item)} accessibilityRole="button" accessibilityLabel={item.title}><Text style={styles.category}>{item.category}</Text><Text style={styles.title}>{item.title}</Text><Text style={styles.summary}>{item.summary}</Text></TouchableOpacity>} ListEmptyComponent={<Text style={styles.empty}>{t("help.empty")}</Text>} />}
      <Modal visible={selected !== null} animationType="slide" onRequestClose={() => setSelected(null)}>
        <ScrollView style={styles.modal}><TouchableOpacity onPress={() => setSelected(null)} accessibilityRole="button"><Text style={styles.close}>{t("common.close")}</Text></TouchableOpacity>{selected && <><Text style={styles.title}>{selected.title}</Text><Text style={styles.body}>{selected.body}</Text><Text style={styles.question}>{t("help.wasHelpful")}</Text><View style={styles.actions}><TouchableOpacity style={styles.answer} onPress={() => rateArticle(selected, true)}><Text style={styles.answerText}>{t("help.yes")}</Text></TouchableOpacity><TouchableOpacity style={styles.answer} onPress={() => rateArticle(selected, false)}><Text style={styles.answerText}>{t("help.no")}</Text></TouchableOpacity></View></>}</ScrollView>
      </Modal>
      <Modal transparent visible={tourVisible} animationType="fade" onRequestClose={() => setTourVisible(false)}><View style={styles.overlay}><View style={styles.tourCard}><Text style={styles.tourHeading}>{t("help.tourTitle")}</Text><Text style={styles.tourBody}>{t(TOUR_KEYS[tourStep])}</Text><Text style={styles.counter}>{tourStep + 1} / {TOUR_KEYS.length}</Text><View style={styles.actions}>{tourStep > 0 && <Pressable onPress={() => setTourStep(tourStep - 1)}><Text style={styles.skip}>{t("help.back")}</Text></Pressable>}<Pressable onPress={tourStep === TOUR_KEYS.length - 1 ? finishTour : () => setTourStep(tourStep + 1)}><Text style={styles.next}>{tourStep === TOUR_KEYS.length - 1 ? t("help.finish") : t("help.next")}</Text></Pressable></View></View></View></Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 16 }, intro: { color: "#bbb", marginBottom: 12 }, tourButton: { backgroundColor: "#302a61", padding: 12, borderRadius: 10, marginBottom: 12 }, tourText: { color: "#fff", fontWeight: "700", textAlign: "center" }, search: { backgroundColor: "#1a1a2e", color: "#fff", padding: 12, borderRadius: 10, marginBottom: 10 }, loading: { marginTop: 40 }, article: { backgroundColor: "#1a1a2e", padding: 16, borderRadius: 12, marginBottom: 10 }, category: { color: "#8c80ff", fontSize: 12, textTransform: "uppercase" }, title: { color: "#fff", fontWeight: "700", fontSize: 19, marginTop: 3 }, summary: { color: "#bbb", marginTop: 7, lineHeight: 20 }, empty: { color: "#888", textAlign: "center", marginTop: 30 }, modal: { flex: 1, backgroundColor: "#0f0f23", padding: 24 }, close: { color: "#9c92ff", marginBottom: 24 }, body: { color: "#ddd", fontSize: 16, lineHeight: 25, marginTop: 18 }, question: { color: "#bbb", marginTop: 30 }, actions: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 14 }, answer: { backgroundColor: "#302a61", borderRadius: 8, paddingVertical: 10, paddingHorizontal: 24 }, answerText: { color: "#fff", fontWeight: "700" }, overlay: { flex: 1, backgroundColor: "#000a", justifyContent: "center", padding: 24 }, tourCard: { backgroundColor: "#1a1a2e", borderRadius: 14, padding: 24 }, tourHeading: { color: "#fff", fontSize: 21, fontWeight: "700" }, tourBody: { color: "#ddd", fontSize: 16, lineHeight: 24, marginTop: 18 }, counter: { color: "#888", marginTop: 18 }, skip: { color: "#bbb", padding: 10 }, next: { color: "#fff", backgroundColor: "#7c6fff", paddingVertical: 10, paddingHorizontal: 18, borderRadius: 8, overflow: "hidden" },
});
