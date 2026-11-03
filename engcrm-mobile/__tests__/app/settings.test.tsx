import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { Linking } from "react-native";

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
