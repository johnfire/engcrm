import { serverForEmail, serverForSession } from "../../services/reviewer-routing";

describe("reviewer server routing", () => {
  it("routes only the designated reviewer account to the isolated server", () => {
    expect(serverForEmail(" Tester367Google@Example.Test ")).toBe("reviewer");
    expect(serverForEmail("someone@example.test")).toBe("production");
  });

  it("only restores an explicitly saved reviewer session", () => {
    expect(serverForSession("reviewer")).toBe("reviewer");
    expect(serverForSession(null)).toBe("production");
    expect(serverForSession("other")).toBe("production");
  });
});
