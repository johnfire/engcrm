import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockReplace = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

const mockClearToken = jest.fn().mockResolvedValue(undefined);
const mockGetRole = jest.fn().mockResolvedValue("admin");
jest.mock("../../services/auth", () => ({
  clearToken: (...args: any[]) => mockClearToken(...args),
  getRole: (...args: any[]) => mockGetRole(...args),
}));

import SettingsScreen from "../../app/(drawer)/settings";

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
  });
});
