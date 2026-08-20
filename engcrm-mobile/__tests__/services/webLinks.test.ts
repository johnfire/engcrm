import { Linking } from "react-native";

import { browsableUrl, openWebsite } from "../../services/webLinks";

const openURL = jest.spyOn(Linking, "openURL");

describe("browsableUrl", () => {
  it("keeps a full url as typed", () => {
    expect(browsableUrl("https://acme.de/kontakt")).toBe("https://acme.de/kontakt");
    expect(browsableUrl("http://acme.de")).toBe("http://acme.de");
  });

  it("assumes https when the scheme is missing", () => {
    expect(browsableUrl("acme.de")).toBe("https://acme.de");
    expect(browsableUrl("www.acme.de/team")).toBe("https://www.acme.de/team");
  });

  it("trims surrounding whitespace", () => {
    expect(browsableUrl("  acme.de\n")).toBe("https://acme.de");
  });

  it("returns null for empty values", () => {
    expect(browsableUrl(null)).toBeNull();
    expect(browsableUrl(undefined)).toBeNull();
    expect(browsableUrl("   ")).toBeNull();
  });

  it("refuses schemes a browser should not be handed", () => {
    expect(browsableUrl("javascript:alert(1)")).toBeNull();
    expect(browsableUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(browsableUrl("mailto:anna@acme.de")).toBeNull();
    expect(browsableUrl("file:///etc/passwd")).toBeNull();
  });

  it("refuses values without a real host", () => {
    expect(browsableUrl("acme")).toBeNull();
    expect(browsableUrl("https://localhost")).toBeNull();
    expect(browsableUrl("n/a")).toBeNull();
  });
});

describe("openWebsite", () => {
  beforeEach(() => jest.clearAllMocks());

  it("opens the normalised url in the device browser", async () => {
    openURL.mockResolvedValue(true);
    expect(await openWebsite("acme.de")).toBe(true);
    expect(openURL).toHaveBeenCalledWith("https://acme.de");
  });

  it("does not open an unusable url", async () => {
    expect(await openWebsite("javascript:alert(1)")).toBe(false);
    expect(openURL).not.toHaveBeenCalled();
  });

  it("reports failure instead of throwing when the browser refuses", async () => {
    openURL.mockRejectedValue(new Error("no handler"));
    expect(await openWebsite("acme.de")).toBe(false);
  });
});
