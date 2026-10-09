import { sourceLabelKey } from "../../services/sourceLabel";
import { translate } from "../../i18n/translate";

describe("sourceLabelKey", () => {
  it("labels known origins, directory imports and anything else", () => {
    expect(sourceLabelKey("manual_mobile")).toBe("source.manual_mobile");
    expect(sourceLabelKey("bavaria_directory_2026-08-19")).toBe("source.directory_import");
    expect(sourceLabelKey(null)).toBe("source.unknown");
    expect(sourceLabelKey("something_new")).toBe("source.unknown");
  });

  it("has a readable English and German label for every key it can return", () => {
    for (const value of ["manual_mobile", "manual_web", "voice", "card_capture", "research_agent", "bavaria_directory_x", null]) {
      for (const language of ["en", "de"] as const) {
        expect(translate(sourceLabelKey(value), language)).not.toMatch(/^\[/);
      }
    }
  });
});
