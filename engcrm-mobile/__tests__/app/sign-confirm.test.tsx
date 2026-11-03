import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { setHandoff } from "../../services/handoff";

// sign-confirm is a drawer screen, so React Navigation keeps its instance
// mounted and reuses it for every scan — same reuse hazard card-confirm
// guards against (issue #18). Each scan drops its payload via setHandoff and
// the screen takes it on focus.
import { Alert } from "react-native";

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

function sign(businessName: string, captureId: number, place: any = null, town?: string) {
  return {
    town,
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

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(1, "Bäckerei Roth", true, null, expect.objectContaining({ town: "Augsburg" })));
  });

  it("rejecting the place passes accept_place=false on save", async () => {
    setHandoff("sign", sign("Bäckerei Roth", 1, place));
    const { getByText } = render(<SignConfirmScreen />);

    fireEvent.press(getByText("Reject — use sign text only"));
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(1, "Bäckerei Roth", false, null, expect.anything()));
  });

  it("has no place banner and defaults accept_place=false when no match was resolved", async () => {
    setHandoff("sign", sign("Unbekannt GmbH", 3, null));
    const { getByText, queryByText } = render(<SignConfirmScreen />);

    expect(queryByText("📍 Matched on Google Places")).toBeNull();
    const alert = jest.spyOn(Alert, "alert").mockImplementation((_t, _m, buttons) => buttons?.[1]?.onPress?.());
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(3, "Unbekannt GmbH", false, null, expect.anything()));
    alert.mockRestore();
  });
});

describe("sign-confirm town and first-contact notes", () => {
  const place = { name: "Bäckerei Roth", place_id: "abc", address: "Hauptstr 1", city: "Augsburg", website: "", phone: "" };
  beforeEach(() => mockConfirmSign.mockClear());

  it("pre-fills the town typed on the scan screen over the Places city", () => {
    setHandoff("sign", sign("Bäckerei Roth", 1, place, "Königsbrunn"));
    const { getByDisplayValue } = render(<SignConfirmScreen />);
    expect(getByDisplayValue("Königsbrunn")).toBeTruthy();
  });

  it("sends town, notes and met-in-person with the save", async () => {
    setHandoff("sign", sign("Bäckerei Roth", 1, null, "Landsberg"));
    const { getByText, getByLabelText, getAllByDisplayValue } = render(<SignConfirmScreen />);
    // Notes is the empty multiline field after business name and town.
    const empty = getAllByDisplayValue("");
    fireEvent.changeText(empty[empty.length - 1], "Owner friendly, call in January");
    fireEvent(getByLabelText("I talked to someone there"), "valueChange", true);
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(mockConfirmSign).toHaveBeenCalledWith(1, "Bäckerei Roth", false, null, {
      town: "Landsberg", notes: "Owner friendly, call in January", metInPerson: true,
    }));
  });

  it("asks before saving a new business without a town, and cancel saves nothing", async () => {
    setHandoff("sign", sign("Unbekannt GmbH", 3, null));
    const alert = jest.spyOn(Alert, "alert").mockImplementation((_t, _m, buttons) => buttons?.[0]?.onPress?.());
    const { getByText } = render(<SignConfirmScreen />);
    fireEvent.press(getByText("Save business"));

    expect(alert).toHaveBeenCalledWith("No town entered", expect.any(String), expect.any(Array));
    expect(mockConfirmSign).not.toHaveBeenCalled();
    alert.mockRestore();
  });

  it("tells the user when the business saved but the notes did not", async () => {
    mockConfirmSign.mockResolvedValueOnce({ contact_id: 1, capture_id: 1, notes_recorded: false });
    setHandoff("sign", sign("Bäckerei Roth", 1, place, "Augsburg"));
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const { getByText } = render(<SignConfirmScreen />);
    fireEvent.press(getByText("Save business"));

    await waitFor(() => expect(alert).toHaveBeenCalledWith(
      "Business saved", expect.stringContaining("the notes could not be"), expect.any(Array),
    ));
    alert.mockRestore();
  });
});
