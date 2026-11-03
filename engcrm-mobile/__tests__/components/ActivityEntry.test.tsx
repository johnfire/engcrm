import { fireEvent, render } from "@testing-library/react-native";

import { ActivityEntry } from "../../components/ActivityEntry";
import { methodLabelKey } from "../../services/activityTypes";

describe("methodLabelKey — names a method as the web pages do", () => {
  it("maps both vocabularies onto one activity type", () => {
    expect(methodLabelKey("in_person", "organization")).toBe("activity.drop_in");
    expect(methodLabelKey("visit", "person")).toBe("activity.drop_in");
    expect(methodLabelKey("call", "person")).toBe("activity.phone");
    expect(methodLabelKey("letter", "organization")).toBe("activity.post_mail");
  });

  it("names next-step entries", () => {
    expect(methodLabelKey("next_step", "person")).toBe("nextStep.title");
    expect(methodLabelKey("next_step_done", "organization")).toBe("nextStep.doneLog");
  });

  it("calls anything untyped a note on an organization, but 'Other' or nothing on a person", () => {
    expect(methodLabelKey("other", "organization")).toBe("activity.note");
    expect(methodLabelKey(null, "organization")).toBe("activity.note");
    expect(methodLabelKey("other", "person")).toBe("personDetail.notes.methodOther");
    expect(methodLabelKey(null, "person")).toBeNull();
  });
});

describe("ActivityEntry", () => {
  it("shows the kind, minutes, offer, judgments and materials left", () => {
    const screen = render(
      <ActivityEntry
        owner="organization"
        entry={{
          when: "28.10.2026",
          method: "in_person",
          durationMinutes: 20,
          offer: "Consulting",
          text: "Met the owner.",
          attitude: ["warm", "skeptical"],
          myRead: ["trustworthy", "nh"],
          materialsLeft: "Flyer",
          nextAction: "Send prices",
          nextActionDate: "2026-11-10",
        }}
      />,
    );
    expect(screen.getByText("Drop-in · 20 min · Consulting")).toBeTruthy();
    expect(screen.getByText("Met the owner.")).toBeTruthy();
    expect(
      screen.getByText("Their attitude: Warm, Skeptical · My read of them: Trustworthy, NH · Materials left: Flyer"),
    ).toBeTruthy();
    expect(screen.getByText(/10\.11\.2026/)).toBeTruthy();
    expect(screen.getByText(/Send prices/)).toBeTruthy();
  });

  it("shows only what is there, and a Delete link when asked", () => {
    const onDelete = jest.fn();
    const screen = render(
      <ActivityEntry
        owner="person"
        entry={{ when: "01.11.2026 09:15", method: null, text: "Quick note" }}
        onDelete={onDelete}
        deleteLabel="Delete"
      />,
    );
    expect(screen.getByText("Quick note")).toBeTruthy();
    expect(screen.queryByText(/min/)).toBeNull();
    expect(screen.queryByText(/Their attitude/)).toBeNull();
    fireEvent.press(screen.getByText("Delete"));
    expect(onDelete).toHaveBeenCalled();
  });
});
