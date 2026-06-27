import { render } from "@testing-library/react-native";
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

import CardConfirmScreen from "../../app/(drawer)/card-confirm";

function card(company: string, captureId: number) {
  return {
    capture_id: captureId,
    is_card: true,
    fields: { company, name: `${company} contact` },
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
