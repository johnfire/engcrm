import { render, waitFor, act } from "@testing-library/react-native";
import { AppState } from "react-native";

let mockSegments: string[] = [];
const mockReplace = jest.fn();
jest.mock("expo-router", () => {
  const Stack: any = ({ children }: any) => children;
  Stack.Screen = () => null;
  return {
    Stack,
    useRouter: () => ({ replace: mockReplace }),
    useSegments: () => mockSegments,
  };
});

const mockIsLoggedIn = jest.fn();
jest.mock("../../services/auth", () => ({
  isLoggedIn: (...args: any[]) => mockIsLoggedIn(...args),
}));

const mockFetchMe = jest.fn();
const mockFetchHelpTourStatus = jest.fn();
jest.mock("../../services/api", () => ({
  ...jest.requireActual("../../services/api"),
  fetchMe: (...args: any[]) => mockFetchMe(...args),
  fetchHelpTourStatus: (...args: any[]) => mockFetchHelpTourStatus(...args),
}));

const mockRegisterForPush = jest.fn().mockResolvedValue(undefined);
let languageChangeCallback: ((language: string) => void) | null = null;
jest.mock("../../services/notifications", () => ({
  registerForPushNotifications: (...args: any[]) => mockRegisterForPush(...args),
  addLanguageChangeListener: (cb: (language: string) => void) => {
    languageChangeCallback = cb;
    return jest.fn();
  },
}));

// _layout.tsx has no text of its own — it wraps a real <Stack>. Rather than
// asserting on rendered UI (there is none), swap in a spy for setLanguage so
// each sync path (cold start / foreground / push) can be verified directly.
const mockSetLanguage = jest.fn();
jest.mock("../../i18n/I18nContext", () => ({
  I18nProvider: ({ children }: any) => children,
  useTranslation: () => ({ language: "en", setLanguage: mockSetLanguage, t: (key: string) => key }),
}));

import RootLayout from "../../app/_layout";

describe("root layout language sync", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockFetchMe.mockReset();
    mockFetchHelpTourStatus.mockReset().mockResolvedValue({ completed: true });
    mockRegisterForPush.mockClear();
    mockSetLanguage.mockClear();
    languageChangeCallback = null;
    mockSegments = ["(drawer)"];
    (AppState.addEventListener as jest.Mock) = jest
      .fn()
      .mockReturnValue({ remove: jest.fn() });
  });

  it("syncs the account language on cold start when logged in", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "de" });

    render(<RootLayout />);

    await waitFor(() => expect(mockFetchMe).toHaveBeenCalledTimes(1));
    expect(mockSetLanguage).toHaveBeenCalledWith("de");
  });

  it("opens the tour for a customer who has not completed it", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "en" });
    mockFetchHelpTourStatus.mockResolvedValue({ completed: false });

    render(<RootLayout />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/(drawer)/help?tour=1"));
  });

  it("does not fetch or sync language when not logged in", async () => {
    mockIsLoggedIn.mockResolvedValue(false);
    mockSegments = ["(drawer)"];

    render(<RootLayout />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(mockFetchMe).not.toHaveBeenCalled();
    expect(mockSetLanguage).not.toHaveBeenCalled();
  });

  it("ignores a failed sync (offline / expired token) instead of throwing", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockRejectedValue(new Error("network"));

    render(<RootLayout />);

    await waitFor(() => expect(mockFetchMe).toHaveBeenCalledTimes(1));
    expect(mockSetLanguage).not.toHaveBeenCalled();
  });

  it("re-syncs the language when the app returns to the foreground", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "en" });

    render(<RootLayout />);
    await waitFor(() => expect(mockFetchMe).toHaveBeenCalledTimes(1));

    const listener = (AppState.addEventListener as jest.Mock).mock.calls[0][1];
    mockFetchMe.mockClear();
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "de" });

    await act(async () => listener("active"));

    expect(mockFetchMe).toHaveBeenCalledTimes(1);
    expect(mockSetLanguage).toHaveBeenCalledWith("de");
  });

  it("applies a language pushed via silent notification without a network call", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "en" });

    render(<RootLayout />);
    await waitFor(() => expect(mockFetchMe).toHaveBeenCalledTimes(1));

    expect(languageChangeCallback).not.toBeNull();
    mockFetchMe.mockClear();
    mockSetLanguage.mockClear();

    act(() => languageChangeCallback!("de"));

    expect(mockFetchMe).not.toHaveBeenCalled();
    expect(mockSetLanguage).toHaveBeenCalledWith("de");
  });

  it("ignores an unsupported language value from a push payload", async () => {
    mockIsLoggedIn.mockResolvedValue(true);
    mockFetchMe.mockResolvedValue({ email: "a@b.com", role: "admin", ui_language: "en" });

    render(<RootLayout />);
    await waitFor(() => expect(mockFetchMe).toHaveBeenCalledTimes(1));

    mockSetLanguage.mockClear();
    act(() => languageChangeCallback!("fr"));

    expect(mockSetLanguage).not.toHaveBeenCalled();
  });
});
