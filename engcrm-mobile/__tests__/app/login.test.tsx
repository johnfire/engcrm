import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import LoginScreen from "../../app/login";

const mockReplace = jest.fn();
const mockLogin = jest.fn();
const mockSaveToken = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ replace: mockReplace, push: jest.fn() }) }));
jest.mock("../../services/api", () => ({
  API_BASE: "https://engcrm.christopherrehm.de", login: (...args: unknown[]) => mockLogin(...args),
  fetchMe: () => Promise.resolve({ ui_language: "en" }),
}));
jest.mock("../../services/auth", () => ({ saveToken: (...args: unknown[]) => mockSaveToken(...args) }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
});

afterEach(() => jest.restoreAllMocks());

function fillLogin() {
  const screen = render(<LoginScreen />);
  fireEvent.changeText(screen.getByPlaceholderText("Email"), "person@example.test");
  fireEvent.changeText(screen.getByPlaceholderText("Password"), "password");
  fireEvent.changeText(screen.getByLabelText("Authenticator or recovery code"), "123456");
  return screen;
}

it("submits the entered second factor before storing a successful session", async () => {
  mockLogin.mockResolvedValue({ token: "verified-token", role: "admin", server: "production" });
  const screen = fillLogin();
  fireEvent.press(screen.getByText("Sign In"));
  await waitFor(() => expect(mockSaveToken).toHaveBeenCalledWith("verified-token", "admin", "production"));
  expect(mockLogin).toHaveBeenCalledWith("person@example.test", "password", "123456");
  expect(mockReplace).toHaveBeenCalledWith("/(drawer)/organizations");
});

it("keeps the user signed out when the server refuses the factor", async () => {
  mockLogin.mockRejectedValue(new Error("Invalid second factor"));
  const screen = fillLogin();
  fireEvent.press(screen.getByText("Sign In"));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalled());
  expect(mockSaveToken).not.toHaveBeenCalled();
  expect(mockReplace).not.toHaveBeenCalled();
});
