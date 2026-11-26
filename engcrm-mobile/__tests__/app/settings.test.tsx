import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { Alert, Linking } from "react-native";
import { useOffline } from "../../services/offline-context";
import { readSyncStatus } from "../../services/sync-status";
import { activateOfflineStorage } from "../../services/offline-enrollment";

jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../services/sync-status", () => ({ readSyncStatus: jest.fn() }));
jest.mock("../../services/offline-enrollment", () => ({ activateOfflineStorage: jest.fn() }));

const mockReplace = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useFocusEffect: (effect: () => void) => jest.requireActual("react").useEffect(effect, [effect]),
}));

// Field mode has its own tests; here it is off, and logging out must stop it.
const mockStopFieldMode = jest.fn().mockResolvedValue(undefined);
jest.mock("../../services/fieldMode", () => ({
  FIELD_MODE_HOURS: 8,
  isFieldModeOn: () => Promise.resolve(false),
  fieldModeEndsAt: () => Promise.resolve(null),
  startFieldMode: jest.fn(),
  stopFieldMode: (...args: any[]) => mockStopFieldMode(...args),
}));

const mockClearToken = jest.fn().mockResolvedValue(undefined);
const mockGetRole = jest.fn().mockResolvedValue("admin");
jest.mock("../../services/auth", () => ({
  clearToken: (...args: any[]) => mockClearToken(...args),
  getRole: (...args: any[]) => mockGetRole(...args),
}));

const mockUpdateLanguage = jest.fn();
jest.mock("../../services/api", () => ({
  ...jest.requireActual("../../services/api"),
  updateLanguage: (...args: any[]) => mockUpdateLanguage(...args),
}));

import SettingsScreen from "../../app/(drawer)/settings";
import { I18nProvider } from "../../i18n/I18nContext";

beforeEach(() => {
  jest.mocked(useOffline).mockReturnValue({ session: null, status: null, state: "disabled", requestSync: jest.fn(),
    refreshStatus: jest.fn(), retryOpen: jest.fn() });
});

describe("settings screen", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockClearToken.mockClear();
  });

  it("shows the signed-in role", async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => expect(getByText("admin")).toBeTruthy());
  });

  it("logs out and returns to login on Log out", async () => {
    const { getByText } = render(<SettingsScreen />);
    fireEvent.press(getByText("Log out"));
    await waitFor(() => expect(mockClearToken).toHaveBeenCalled());
    expect(mockReplace).toHaveBeenCalledWith("/login");
    // Field mode stops (and sends its queue) while the login it uploads under still works.
    expect(mockStopFieldMode).toHaveBeenCalled();
    expect(mockStopFieldMode.mock.invocationCallOrder[0]).toBeLessThan(mockClearToken.mock.invocationCallOrder[0]);
  });

  it("protects unsent offline edits when signing out from Settings", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    jest.mocked(useOffline).mockReturnValue({ session: { database: {} } as never, status: null, state: "idle",
      requestSync: jest.fn(), refreshStatus: jest.fn(), retryOpen: jest.fn() });
    jest.mocked(readSyncStatus).mockResolvedValue({ ready: true, pending: 1, failed: 0, review: 0, lastSuccessAt: null, upToDate: false });
    const view = render(<SettingsScreen />);
    fireEvent.press(view.getByText("Log out"));
    await waitFor(() => expect(alert).toHaveBeenCalled());
    expect(mockClearToken).not.toHaveBeenCalled();
    const buttons = alert.mock.calls[0][2]!;
    buttons.find((button) => button.text === "Sign out and keep edits")!.onPress!();
    await waitFor(() => expect(mockClearToken).toHaveBeenCalledTimes(1));
    alert.mockRestore();
  });

  it("lets an admin opt in to offline mode when the server permits it", async () => {
    const retryOpen = jest.fn();
    jest.mocked(useOffline).mockReturnValue({ session: null, status: null, state: "disabled", requestSync: jest.fn(),
      refreshStatus: jest.fn(), retryOpen });
    jest.mocked(activateOfflineStorage).mockResolvedValue();
    const view = render(<SettingsScreen />);
    await waitFor(() => expect(view.getByText("Enable offline mode")).toBeTruthy());
    fireEvent.press(view.getByText("Enable offline mode"));
    await waitFor(() => expect(activateOfflineStorage).toHaveBeenCalled());
    await waitFor(() => expect(retryOpen).toHaveBeenCalled());
  });

  it("opens the Impressum page in the browser", async () => {
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => expect(getByText("admin")).toBeTruthy());
    fireEvent.press(getByText("Impressum"));
    expect(openURL).toHaveBeenCalledWith("https://engcrm.christopherrehm.de/impressum");
    openURL.mockRestore();
  });
});

describe("settings screen language picker", () => {
  beforeEach(() => {
    mockUpdateLanguage.mockReset().mockResolvedValue({ ui_language: "de" });
  });

  it("switches to German immediately and calls the API", async () => {
    const { getByText, queryByText } = render(
      <I18nProvider>
        <SettingsScreen />
      </I18nProvider>,
    );
    await waitFor(() => expect(getByText("admin")).toBeTruthy());

    fireEvent.press(getByText("Deutsch"));

    await waitFor(() => expect(mockUpdateLanguage).toHaveBeenCalledWith("de"));
    // UI applied the switch immediately — no need to wait for the API call
    expect(getByText("Abmelden")).toBeTruthy(); // settings.logout in German
    expect(queryByText("Log out")).toBeNull();
  });

  it("reverts to English if the API call fails", async () => {
    mockUpdateLanguage.mockRejectedValue(new Error("network"));
    const { getByText, queryByText } = render(
      <I18nProvider>
        <SettingsScreen />
      </I18nProvider>,
    );
    await waitFor(() => expect(getByText("admin")).toBeTruthy());

    fireEvent.press(getByText("Deutsch"));

    await waitFor(() => expect(mockUpdateLanguage).toHaveBeenCalledWith("de"));
    await waitFor(() => expect(getByText("Log out")).toBeTruthy());
    expect(queryByText("Abmelden")).toBeNull();
  });
});
