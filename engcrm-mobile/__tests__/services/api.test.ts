import { buildHeaders, API_BASE } from "../../services/api";

describe("api service", () => {
  it("uses the correct base URL", () => {
    expect(API_BASE).toBe("https://engcrm.christopherrehm.de");
  });

  it("buildHeaders includes Authorization when token provided", () => {
    const headers = buildHeaders("my-jwt-token");
    expect(headers["Authorization"]).toBe("Bearer my-jwt-token");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("buildHeaders works without token", () => {
    const headers = buildHeaders(null);
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["Authorization"]).toBeUndefined();
  });
});
