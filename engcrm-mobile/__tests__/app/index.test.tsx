import { render, waitFor } from "@testing-library/react-native";
import { Redirect } from "expo-router";

// The root route must always send you somewhere — this is the regression guard
// for the "Unmatched Route" bug (a missing/ broken root redirect).
jest.mock("expo-router", () => ({ Redirect: jest.fn(() => null) }));
jest.mock("../../services/auth", () => ({ isLoggedIn: jest.fn() }));

import Index from "../../app/index";
import { isLoggedIn } from "../../services/auth";

const redirectMock = Redirect as unknown as jest.Mock;

describe("root index auth gate", () => {
  beforeEach(() => redirectMock.mockClear());

  it("redirects to the drawer when logged in", async () => {
    (isLoggedIn as jest.Mock).mockResolvedValue(true);
    render(<Index />);
    await waitFor(() => expect(redirectMock).toHaveBeenCalled());
    expect(redirectMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({ href: "/(drawer)/organizations" }),
    );
  });

  it("redirects to login when logged out", async () => {
    (isLoggedIn as jest.Mock).mockResolvedValue(false);
    render(<Index />);
    await waitFor(() => expect(redirectMock).toHaveBeenCalled());
    expect(redirectMock.mock.calls[0][0]).toEqual(expect.objectContaining({ href: "/login" }));
  });
});
