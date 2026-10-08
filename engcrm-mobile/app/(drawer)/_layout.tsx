import { Drawer } from "expo-router/drawer";
import { TouchableOpacity, Text } from "react-native";
import { useRouter, type Href } from "expo-router";
import { clearToken } from "../../services/auth";
import { useTranslation } from "../../i18n/I18nContext";

function LogoutButton() {
  const router = useRouter();
  const { t } = useTranslation();
  async function handleLogout() {
    await clearToken();
    router.replace("/login");
  }
  return (
    <TouchableOpacity onPress={handleLogout} style={{ padding: 16 }}>
      <Text style={{ color: "#ef4444", fontSize: 14 }}>{t("settings.logout")}</Text>
    </TouchableOpacity>
  );
}

// Back arrow for drill-down detail screens. They live in the drawer, so their
// default header shows a hamburger — wrong for a detail view, and the drawer's
// back behaviour would otherwise jump to the first screen (Approvals). This
// goes back to where the user came from (Search, a list, the previous screen) and
// only falls back to the owning list when there is nothing to go back to.
function HeaderBack({ to }: { to: Href }) {
  const router = useRouter();
  return (
    <TouchableOpacity
      onPress={() => (router.canGoBack() ? router.back() : router.navigate(to))}
      style={{ paddingHorizontal: 16, paddingVertical: 8 }}
      accessibilityRole="button"
      accessibilityLabel="Back"
    >
      <Text style={{ color: "#fff", fontSize: 26, lineHeight: 26 }}>‹</Text>
    </TouchableOpacity>
  );
}

export default function DrawerLayout() {
  const { t } = useTranslation();
  return (
    <Drawer
      backBehavior="history"
      screenOptions={{
        headerStyle: { backgroundColor: "#0f0f23" },
        headerTintColor: "#fff",
        drawerStyle: { backgroundColor: "#0f0f23" },
        drawerActiveTintColor: "#7c6fff",
        drawerInactiveTintColor: "#888",
        drawerLabelStyle: { fontSize: 15 },
        headerRight: () => <LogoutButton />,
      }}
    >
      <Drawer.Screen
        name="search"
        options={{ title: t("drawer.searchTitle"), drawerLabel: t("drawer.search") }}
      />
      <Drawer.Screen
        name="contacts"
        options={{ title: t("contactFeed.title"), drawerLabel: t("drawer.contacts") }}
      />
      <Drawer.Screen
        name="organizations"
        options={{ title: t("drawer.organizations"), drawerLabel: t("drawer.organizations") }}
      />
      <Drawer.Screen
        name="reachable"
        options={{ title: t("drawer.reachableTitle"), drawerLabel: t("drawer.reachable") }}
      />
      <Drawer.Screen
        name="approvals"
        options={{ title: t("drawer.approvals"), drawerLabel: t("drawer.approvals") }}
      />
      <Drawer.Screen
        name="capture"
        options={{ title: t("drawer.scanCardTitle"), drawerLabel: t("drawer.scanCard") }}
      />
      <Drawer.Screen
        name="scan-document"
        options={{ title: t("drawer.scanDocumentTitle"), drawerLabel: t("drawer.scanDocument") }}
      />
      <Drawer.Screen
        name="scan-sign"
        options={{ title: t("drawer.scanSignTitle"), drawerLabel: t("drawer.scanSign") }}
      />
      <Drawer.Screen
        name="card-queue"
        options={{ title: t("drawer.cardQueueTitle"), drawerLabel: t("drawer.cardQueue") }}
      />
      <Drawer.Screen
        name="voice"
        options={{ title: t("drawer.voiceEntryTitle"), drawerLabel: t("drawer.voiceEntry") }}
      />
      <Drawer.Screen
        name="inbox"
        options={{ title: t("drawer.inbox"), drawerLabel: t("drawer.inbox") }}
      />
      <Drawer.Screen
        name="people"
        options={{ title: t("drawer.peopleTitle"), drawerLabel: t("drawer.people") }}
      />
      <Drawer.Screen
        name="recon"
        options={{ title: t("drawer.reconTitle"), drawerLabel: t("drawer.recon") }}
      />
      <Drawer.Screen
        name="activity"
        options={{ title: t("drawer.activity"), drawerLabel: t("drawer.activity") }}
      />
      <Drawer.Screen
        name="research"
        options={{ title: t("drawer.researchTitle"), drawerLabel: t("drawer.research") }}
      />
      <Drawer.Screen
        name="settings"
        options={{ title: t("drawer.settingsTitle"), drawerLabel: t("drawer.settings") }}
      />
      <Drawer.Screen
        name="help"
        options={{ title: t("drawer.helpTitle"), drawerLabel: t("drawer.help") }}
      />
      <Drawer.Screen
        name="organization-detail"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("drawer.organization"),
          headerLeft: () => <HeaderBack to="/(drawer)/organizations" />,
        }}
      />
      <Drawer.Screen
        name="person-detail"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("drawer.person"),
          headerLeft: () => <HeaderBack to="/(drawer)/people" />,
        }}
      />
      <Drawer.Screen
        name="log-meeting"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("meeting.title"),
          headerLeft: () => <HeaderBack to="/(drawer)/search" />,
        }}
      />
      <Drawer.Screen name="saved-messages" options={{ drawerItemStyle: { display: "none" },
        title: t("savedMessages.button"), headerLeft: () => <HeaderBack to="/(drawer)/people" /> }} />
      <Drawer.Screen name="contact-date" options={{ drawerItemStyle: { display: "none" },
        title: t("contactDate.title"), headerLeft: () => <HeaderBack to="/(drawer)/contacts" /> }} />
      <Drawer.Screen
        name="edit-organization"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("recordForm.organizationTitle"),
          headerLeft: () => <HeaderBack to="/(drawer)/search" />,
        }}
      />
      <Drawer.Screen
        name="edit-person"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("recordForm.personTitle"),
          headerLeft: () => <HeaderBack to="/(drawer)/search" />,
        }}
      />
      <Drawer.Screen
        name="card-confirm"
        options={{ drawerItemStyle: { display: "none" }, title: t("drawer.reviewCard") }}
      />
      <Drawer.Screen
        name="voice-confirm"
        options={{ drawerItemStyle: { display: "none" }, title: t("drawer.voiceNote") }}
      />
      <Drawer.Screen
        name="sign-confirm"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("drawer.reviewSign"),
          headerLeft: () => <HeaderBack to="/(drawer)/scan-sign" />,
        }}
      />
      <Drawer.Screen
        name="area-scan"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("drawer.areaScanTitle"),
          headerLeft: () => <HeaderBack to="/(drawer)/research" />,
        }}
      />
      <Drawer.Screen
        name="area-results"
        options={{
          drawerItemStyle: { display: "none" },
          title: t("drawer.areaResultsTitle"),
          headerLeft: () => <HeaderBack to="/(drawer)/research" />,
        }}
      />
    </Drawer>
  );
}
