import type { ReactNode } from "react";
import type { StyleProp, ViewStyle } from "react-native";
import { SafeAreaProvider, SafeAreaView, type Edge } from "react-native-safe-area-context";

// A React Native Modal opens its own Android window, drawn edge-to-edge
// (edgeToEdgeEnabled=true forces it). The padding the root layout gives every
// screen does not reach that window, so without this a modal's buttons sit under
// the back/home/recents bar. Bottom sheets pass ["bottom"]; full-screen modals
// pass ["top", "bottom"] because they also cover the status bar.
export function ModalSafeArea({ edges, style, children }: {
  edges: Edge[];
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
}) {
  return (
    <SafeAreaProvider>
      <SafeAreaView testID="modal-safe-area" edges={edges} style={[{ flex: 1 }, style]}>
        {children}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
