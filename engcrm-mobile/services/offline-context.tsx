import * as Network from "expo-network";
import Constants from "expo-constants";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { openOfflineSession } from "./offline-session";
import { hasActivatedOfflineStorage } from "./offline-activation";
import { synchronizeOfflineSession } from "./offline-sync-session";
import { createSyncCoordinator, type CoordinatorState } from "./sync-coordinator";
import { readSyncStatus, type SyncStatus } from "./sync-status";

type OfflineSession = Awaited<ReturnType<typeof openOfflineSession>>;
interface OfflineContextValue {
  session: OfflineSession | null;
  status: SyncStatus | null;
  state: "disabled" | "opening" | CoordinatorState;
  requestSync(): void;
  refreshStatus(): Promise<void>;
  retryOpen(): void;
}

const defaults: OfflineContextValue = { session: null, status: null, state: "disabled", requestSync: () => {},
  refreshStatus: async () => {}, retryOpen: () => {} };
const OfflineContext = createContext<OfflineContextValue>(defaults);

export function useOffline(): OfflineContextValue { return useContext(OfflineContext); }

function EnabledProvider({ children, requireActivation = false }: { children: ReactNode; requireActivation?: boolean }) {
  const [session, setSession] = useState<OfflineSession | null>(null);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [state, setState] = useState<OfflineContextValue["state"]>("opening");
  const [attempt, setAttempt] = useState(0);
  const coordinator = useRef<ReturnType<typeof createSyncCoordinator> | null>(null);
  const requestSync = useCallback(() => coordinator.current?.trigger(), []);
  const retryOpen = useCallback(() => {
    setSession(null);
    setStatus(null);
    setState("opening");
    setAttempt((previous) => previous + 1);
  }, []);
  const refreshStatus = useCallback(async () => {
    if (session) setStatus(await readSyncStatus(session.database));
  }, [session]);

  useEffect(() => {
    let live = true;
    let connected: boolean | null = null;
    let network: { remove(): void } | null = null;
    let foreground: { remove(): void } | null = null;
    openOfflineSession(requireActivation).then(async (opened) => {
      if (!live) return;
      setSession(opened);
      const initialStatus = await readSyncStatus(opened.database);
      if (!live) return;
      setStatus(initialStatus);
      coordinator.current = createSyncCoordinator(async () => {
        try {
          await synchronizeOfflineSession(opened, Constants.expoConfig?.version ?? "unknown");
        } finally {
          const current = await readSyncStatus(opened.database);
          if (live) setStatus(current);
        }
      }, (next) => { if (live) setState(next); });
      network = Network.addNetworkStateListener((connection) => {
        const online = !!connection.isConnected && connection.isInternetReachable !== false;
        if (online && connected !== true) coordinator.current?.trigger();
        connected = online;
      });
      foreground = AppState.addEventListener("change", (next) => { if (next === "active") coordinator.current?.trigger(); });
      coordinator.current.trigger();
    }).catch(() => { if (live) setState("error"); });
    return () => {
      live = false;
      coordinator.current?.stop();
      coordinator.current = null;
      network?.remove();
      foreground?.remove();
    };
  }, [attempt, requireActivation]);

  return <OfflineContext.Provider value={{ session, status, state, requestSync, refreshStatus, retryOpen }}>{children}</OfflineContext.Provider>;
}

export function OfflineProvider({ children, enabled = process.env.EXPO_PUBLIC_OFFLINE_CACHE === "true" }: { children: ReactNode; enabled?: boolean }) {
  const [recovery, setRecovery] = useState<"checking" | "active" | "inactive" | "error">("checking");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (enabled) return;
    let active = true;
    hasActivatedOfflineStorage().then((activated) => {
      if (active) setRecovery(activated ? "active" : "inactive");
    }).catch(() => { if (active) setRecovery("error"); });
    return () => { active = false; };
  }, [enabled, attempt]);
  const retryOpen = () => { setRecovery("checking"); setAttempt((previous) => previous + 1); };
  if (enabled || recovery === "active") return <EnabledProvider requireActivation={!enabled}>{children}</EnabledProvider>;
  if (recovery === "inactive") return <OfflineContext.Provider value={{ ...defaults, retryOpen }}>{children}</OfflineContext.Provider>;
  const state = recovery === "error" ? "error" : "opening";
  return <OfflineContext.Provider value={{ ...defaults, state, retryOpen }}>{children}</OfflineContext.Provider>;
}
