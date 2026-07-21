import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { setHandoff } from "../../services/handoff";

// sign-confirm is a drawer screen, so React Navigation keeps its instance
// mounted and reuses it for every scan — same reuse hazard card-confirm
// guards against (issue #18). Each scan drops its payload via setHandoff and
// the screen takes it on focus.
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), navigate: jest.fn() }),
  useFocusEffect: (cb: () => void) => cb(),
}));

const mockConfirmSign = jest.fn().mockResolvedValue({ contact_id: 1, capture_id: 1 });
const mockDiscardSign = jest.fn().mockResolvedValue(undefined);
jest.mock("../../services/api", () => ({
  confirmSign: (...args: any[]) => mockConfirmSign(...args),
  discardSign: (...args: any[]) => mockDiscardSign(...args),
}));

import SignConfirmScreen from "../../app/(drawer)/sign-confirm";

function sign(businessName: string, captureId: number, place: any = null) {
  return {
    capture_id: captureId,
    is_sign: true,
    confidence: 80,
    fields: { business_name: businessName },
    place,
    dup_suggestion: null,
    cost_usd: 0.001,
  };
}

describe("sign-confirm re-seeds on a new capture", () => {
  it("shows the second sign's business name after the screen is reused", () => {
    setHandoff("sign", sign("Bäckerei Roth", 1));
    const { rerender, getByDisplayValue, queryByDisplayValue } = render(<SignConfirmScreen />);
    expect(getByDisplayValue("Bäckerei Roth")).toBeTruthy();

    setHandoff("sign", sign("Café Klein", 2));
    rerender(<SignConfirmScreen />);

    expect(getByDisplayValue("Café Klein")).toBeTruthy();
    expect(queryByDisplayValue("Bäckerei Roth")).toBeNull();
  });
});

describe("sign-confirm Places accept/reject guardrail", () => {
  const place = { name: "Bäckerei Roth", place_id: "abc", address: "Hauptstr 1", city: "Augsburg", website: "", phone: "" };

  it("defaults to accepting the resolved place and passes accept_place=true on save", async () => {
    setHandoff("sign", sign("Bäckerei Roth", 1, place));
    const { getByText } = render(<SignConfirmScreen />);

    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(1, "Bäckerei Roth", true, null));
  });

  it("rejecting the place passes accept_place=false on save", async () => {
    setHandoff("sign", sign("Bäckerei Roth", 1, place));
    const { getByText } = render(<SignConfirmScreen />);

    fireEvent.press(getByText("Reject — use sign text only"));
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(1, "Bäckerei Roth", false, null));
  });

  it("has no place banner and defaults accept_place=false when no match was resolved", async () => {
    setHandoff("sign", sign("Unbekannt GmbH", 3, null));
    const { getByText, queryByText } = render(<SignConfirmScreen />);

    expect(queryByText("📍 Matched on Google Places")).toBeNull();
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(3, "Unbekannt GmbH", false, null));
  });
});
