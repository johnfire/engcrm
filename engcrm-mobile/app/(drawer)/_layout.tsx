import { Drawer } from "expo-router/drawer";
import { TouchableOpacity, Text } from "react-native";
import { useRouter } from "expo-router";
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

export default function DrawerLayout() {
  return (
    <Drawer
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
        name="inbox"
        options={{ title: "Inbox", drawerLabel: "Inbox" }}
      />
      <Drawer.Screen
        name="contacts"
        options={{ title: "Contacts", drawerLabel: "Contacts" }}
      />
      <Drawer.Screen
        name="activity"
        options={{ title: "Activity", drawerLabel: "Activity" }}
      />
      <Drawer.Screen
        name="research"
        options={{ title: "Research", drawerLabel: "Research" }}
      />
      <Drawer.Screen
        name="contact-detail"
        options={{ drawerItemStyle: { display: "none" }, title: "Contact" }}
      />
      <Drawer.Screen
        name="card-confirm"
        options={{ drawerItemStyle: { display: "none" }, title: "Review Card" }}
      />
    </Drawer>
  );
}
