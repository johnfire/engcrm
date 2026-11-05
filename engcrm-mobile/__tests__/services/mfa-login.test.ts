import { client, login } from "../../services/api";

describe("two-factor login transport", () => {
  it("sends the second factor to the account's selected server", async () => {
    const post = jest.spyOn(client, "post").mockResolvedValue({ data: { token: "test", role: "admin" } });
    await login("tester367google@example.test", "password", "recovery-code");
    expect(post).toHaveBeenCalledWith("/api/auth/token", {
      email: "tester367google@example.test", password: "password", mfa_code: "recovery-code",
    }, { baseURL: "https://engcrm.christopherrehm.de/reviewer" });
    post.mockRestore();
  });
});
