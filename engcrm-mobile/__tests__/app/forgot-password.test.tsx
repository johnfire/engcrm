import { render, fireEvent, waitFor } from "@testing-library/react-native";

const mockReplace = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}));

const mockRequestPasswordReset = jest.fn().mockResolvedValue(undefined);
jest.mock("../../services/api", () => ({
  requestPasswordReset: (...args: any[]) => mockRequestPasswordReset(...args),
}));

import ForgotPasswordScreen from "../../app/forgot-password";

describe("forgot-password screen", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockRequestPasswordReset.mockClear();
  });

  it("submits the email and shows the generic confirmation", async () => {
    const { getByPlaceholderText, getByText, queryByPlaceholderText } = render(
      <ForgotPasswordScreen />,
    );
    fireEvent.changeText(getByPlaceholderText("Email"), "a@b.com");
    fireEvent.press(getByText("Send reset link"));

    await waitFor(() => expect(mockRequestPasswordReset).toHaveBeenCalledWith("a@b.com"));
    expect(getByText(/we've sent a link/)).toBeTruthy();
    expect(queryByPlaceholderText("Email")).toBeNull();
  });

  it("shows the same confirmation even if the request fails (never leaks account state)", async () => {
    mockRequestPasswordReset.mockRejectedValueOnce(new Error("network"));
    const { getByPlaceholderText, getByText } = render(<ForgotPasswordScreen />);
    fireEvent.changeText(getByPlaceholderText("Email"), "a@b.com");
    fireEvent.press(getByText("Send reset link"));

    await waitFor(() => expect(getByText(/we've sent a link/)).toBeTruthy());
  });

  it("back to sign in navigates to /login", () => {
    const { getByText } = render(<ForgotPasswordScreen />);
    fireEvent.press(getByText("Back to sign in"));
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });
});
