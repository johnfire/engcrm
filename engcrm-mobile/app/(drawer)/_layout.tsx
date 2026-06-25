import { Drawer } from "expo-router/drawer";
import { TouchableOpacity, Text } from "react-native";
import { useRouter, type Href } from "expo-router";
import { clearToken } from "../../services/auth";

function LogoutButton() {
  const router = useRouter();
  async function handleLogout() {
    await clearToken();
    router.replace("/login");
  }
  return (
    <TouchableOpacity onPress={handleLogout} style={{ padding: 16 }}>
      <Text style={{ color: "#ef4444", fontSize: 14 }}>Log out</Text>
    </TouchableOpacity>
  );
}

// Back arrow for drill-down detail screens. They live in the drawer, so their
// default header shows a hamburger — wrong for a detail view, and the drawer's
// back behaviour would otherwise jump to the first screen (Approvals). This
// returns explicitly to the owning list (Contacts / People) regardless of how
// the detail was reached.
function HeaderBack({ to }: { to: Href }) {
  const router = useRouter();
  return (
    <TouchableOpacity
      onPress={() => router.navigate(to)}
      style={{ paddingHorizontal: 16, paddingVertical: 8 }}
      accessibilityRole="button"
      accessibilityLabel="Back"
    >
      <Text style={{ color: "#fff", fontSize: 26, lineHeight: 26 }}>‹</Text>
    </TouchableOpacity>
  );
}

export default function DrawerLayout() {
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
        name="approvals"
        options={{ title: "Approvals", drawerLabel: "Approvals" }}
      />
      <Drawer.Screen
        name="capture"
        options={{ title: "Scan Card", drawerLabel: "📷 Scan Card" }}
      />
      <Drawer.Screen
        name="card-queue"
        options={{ title: "Card Queue", drawerLabel: "🗂 Card Queue" }}
      />
      <Drawer.Screen
        name="voice"
        options={{ title: "Voice Entry", drawerLabel: "🎙 Voice Entry" }}
      />
      <Drawer.Screen
        name="inbox"
        options={{ title: "Inbox", drawerLabel: "Inbox" }}
      />
      <Drawer.Screen
        name="contacts"
        options={{ title: "Contacts", drawerLabel: "Contacts" }}
      />
      <Drawer.Screen
        name="people"
        options={{ title: "People", drawerLabel: "👤 People" }}
      />
      <Drawer.Screen
        name="recon"
        options={{ title: "Recon", drawerLabel: "🧭 Recon (near me)" }}
      />
      <Drawer.Screen
        name="activity"
        options={{ title: "Activity", drawerLabel: "Activity" }}
      />
      <Drawer.Screen
        name="research"
        options={{ title: "Research", drawerLabel: "🔬 Research" }}
      />
      <Drawer.Screen
        name="contact-detail"
        options={{
          drawerItemStyle: { display: "none" },
          title: "Contact",
          headerLeft: () => <HeaderBack to="/(drawer)/contacts" />,
        }}
      />
      <Drawer.Screen
        name="person-detail"
        options={{
          drawerItemStyle: { display: "none" },
          title: "Person",
          headerLeft: () => <HeaderBack to="/(drawer)/people" />,
        }}
      />
      <Drawer.Screen
        name="card-confirm"
        options={{ drawerItemStyle: { display: "none" }, title: "Review Card" }}
      />
      <Drawer.Screen
        name="voice-confirm"
        options={{ drawerItemStyle: { display: "none" }, title: "Voice Note" }}
      />
    </Drawer>
  );
}
