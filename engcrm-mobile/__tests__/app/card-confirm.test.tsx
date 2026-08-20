import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { setHandoff } from "../../services/handoff";

// card-confirm is a drawer screen, so React Navigation keeps its instance
// mounted and reuses it for every scan. This guards issue #18: the second card
// must show the second card's fields, not the first card's. Each scan drops its
// payload via setHandoff and the screen takes it on focus.
const mockFocusCallbacks: Array<() => void> = [];
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), navigate: jest.fn() }),
  // Run the focus callback immediately, mirroring a screen gaining focus.
  useFocusEffect: (cb: () => void) => {
    mockFocusCallbacks.push(cb);
    cb();
  },
}));
jest.mock("../../services/api", () => ({
  confirmCard: jest.fn(),
  discardCard: jest.fn(),
}));

import { confirmCard } from "../../services/api";
import CardConfirmScreen from "../../app/(drawer)/card-confirm";

function card(company: string, captureId: number) {
  return {
    capture_id: captureId,
    is_card: true,
    fields: { company, name: `${company} organization` },
  };
}

describe("card-confirm re-seeds on a new capture", () => {
  it("shows the second card's fields after the screen is reused", () => {
    setHandoff("card", card("Acme GmbH", 1));
    const { rerender, getByDisplayValue, queryByDisplayValue } = render(<CardConfirmScreen />);
    expect(getByDisplayValue("Acme GmbH")).toBeTruthy();

    // Same mounted instance regains focus with a fresh capture waiting (2nd scan).
    setHandoff("card", card("Globex Ltd", 2));
    rerender(<CardConfirmScreen />);

    expect(getByDisplayValue("Globex Ltd")).toBeTruthy();
    expect(queryByDisplayValue("Acme GmbH")).toBeNull();
  });
});

// "Met at" is the one field no card carries — it's typed on this screen before
// the lead is saved — so it has to survive the edit and reach confirmCard.
describe("card-confirm met-at field", () => {
  it("sends the edited met_at with the confirmed fields", async () => {
    setHandoff("card", {
      capture_id: 7,
      is_card: true,
      fields: { company: "Acme GmbH", name: "Anna Roth", met_at: "Kunstmesse" },
    });
    const { getByDisplayValue, getByText } = render(<CardConfirmScreen />);

    fireEvent.changeText(getByDisplayValue("Kunstmesse"), "Gallery opening, Augsburg");
    fireEvent.press(getByText("Save lead"));

    await waitFor(() => expect(confirmCard).toHaveBeenCalled());
    expect((confirmCard as jest.Mock).mock.calls[0][1]).toMatchObject({
      met_at: "Gallery opening, Augsburg",
    });
  });
});
