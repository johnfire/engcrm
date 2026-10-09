import {
  Drawer,
  DrawerContentScrollView,
  DrawerItemList,
  type DrawerContentComponentProps,
} from "expo-router/drawer";
import { useEffect } from "react";
import { AppState, TouchableOpacity, Text, View } from "react-native";
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

// Menu body with a Close button pinned above the scrolling list. The drawer can
// otherwise get stuck open (overlay tap / swipe not registering), which locks the
// whole app — this button is inside the drawer itself so it always works.
function CustomDrawerContent(props: DrawerContentComponentProps) {
  const { t } = useTranslation();
  const { navigation } = props;
  // Returning from the camera or another app can leave the drawer open with its
  // gesture state stale (the stuck menu seen right after a card photo). Always
  // come back with the menu closed.
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") navigation.closeDrawer();
    });
    return () => subscription.remove();
  }, [navigation]);
  return (
    <View style={{ flex: 1 }}>
      <TouchableOpacity
        onPress={() => props.navigation.closeDrawer()}
        style={{
          paddingHorizontal: 20,
          paddingTop: 48,
          paddingBottom: 16,
          borderBottomWidth: 1,
          borderBottomColor: "#2a2a45",
        }}
        accessibilityRole="button"
        accessibilityLabel={t("drawer.closeMenu")}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Text style={{ color: "#fff", fontSize: 18, fontWeight: "600" }}>{t("drawer.closeMenu")}</Text>
      </TouchableOpacity>
      <DrawerContentScrollView {...props}>
        <DrawerItemList {...props} />
      </DrawerContentScrollView>
    </View>
  );
}

export default function DrawerLayout() {
  const { t } = useTranslation();
  return (
    <Drawer
      backBehavior="history"
      drawerContent={(props) => <CustomDrawerContent {...props} />}
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
