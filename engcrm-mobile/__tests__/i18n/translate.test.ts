import { translate, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, isSupportedLanguage } from "../../i18n/translate";

describe("translate", () => {
  it("resolves a key per language", () => {
    expect(translate("drawer.organizations", "en")).toBe("Organizations");
    expect(translate("drawer.organizations", "de")).toBe("Organisationen");
  });

  it("interpolates {{var}} placeholders", () => {
    expect(translate("organizationDetail.score", "en", { score: 80 })).toBe("Score: 80");
    expect(translate("organizationDetail.score", "de", { score: 80 })).toBe("Score: 80");
  });

  it("picks the _one/_other pluralized variant from a count param", () => {
    expect(translate("capture.pending", "en", { count: 1 })).toBe(
      "1 card waiting to upload — tap to retry",
    );
    expect(translate("capture.pending", "en", { count: 3 })).toBe(
      "3 cards waiting to upload — tap to retry",
    );
  });

  it("falls back to a visible marker for a missing key", () => {
    expect(translate("totally.made.up.key", "en")).toBe("[totally.made.up.key]");
  });

  it("defaults language and exposes the supported set", () => {
    expect(DEFAULT_LANGUAGE).toBe("en");
    expect(SUPPORTED_LANGUAGES).toEqual(["en", "de"]);
  });

  it("validates a language value", () => {
    expect(isSupportedLanguage("de")).toBe(true);
    expect(isSupportedLanguage("fr")).toBe(false);
    expect(isSupportedLanguage(null)).toBe(false);
  });
});
