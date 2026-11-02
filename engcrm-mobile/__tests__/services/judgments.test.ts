import { ATTITUDES, MY_READS, toggled } from "../../services/judgments";

describe("judgments", () => {
  it("holds the same values as the server", () => {
    expect(ATTITUDES).toEqual(["warm", "neutral", "cold", "skeptical"]);
    expect(MY_READS).toEqual(["trustworthy", "straightforward", "cant_tell", "holding_back", "story_doesnt_add_up",
      "not_truthful", "indecisive", "confused", "nh", "cf"]);
  });

  it("toggles a value in or out, keeping the list's order", () => {
    expect(toggled(["cold"], "warm", ATTITUDES)).toEqual(["warm", "cold"]);
    expect(toggled(["warm", "cold"], "warm", ATTITUDES)).toEqual(["cold"]);
    expect(toggled([], "nh", MY_READS)).toEqual(["nh"]);
  });
});
