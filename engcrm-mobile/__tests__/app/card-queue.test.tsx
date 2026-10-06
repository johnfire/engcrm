import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { takeHandoff } from "../../services/handoff";

const mockPush = jest.fn();
const mockPending = jest.fn();
jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  return { useRouter: () => ({ push: mockPush }), useFocusEffect: (cb: () => void) => React.useEffect(cb, [cb]) };
});
jest.mock("../../services/api", () => ({ listPendingCards: () => mockPending() }));
import CardQueueScreen from "../../app/(drawer)/card-queue";

beforeEach(() => jest.clearAllMocks());

it("opens document rows for editable review and returns to the queue after saving", async () => {
  mockPending.mockResolvedValue([{ id: 5, kind: "document", extracted: { company: "ACME", name: "Ann" },
    confidence: 90, captured_at: "2026-10-06T12:00:00Z", dup_suggestion: { id: 7, name: "ACME" } }]);
  const screen = render(<CardQueueScreen />);
  await waitFor(() => expect(screen.getByText("ACME")).toBeTruthy());
  expect(screen.getByText("From a photographed page")).toBeTruthy();
  fireEvent.press(screen.getByText("ACME"));
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/card-confirm");
  expect(takeHandoff("card")).toEqual(expect.objectContaining({ capture_id: 5, return_to_queue: true,
    fields: { company: "ACME", name: "Ann" }, dup_suggestion: { id: 7, name: "ACME" } }));
});

it("routes sign drafts to their own confirmation screen with the matched place", async () => {
  mockPending.mockResolvedValue([{ id: 9, kind: "sign", extracted: { business_name: "Bakery" },
    confidence: 80, captured_at: "2026-10-06T12:00:00Z", place_json: { name: "Bakery", city: "Augsburg" } }]);
  const screen = render(<CardQueueScreen />);
  await waitFor(() => expect(screen.getByText("Bakery")).toBeTruthy());
  fireEvent.press(screen.getByText("Bakery"));
  expect(mockPush).toHaveBeenCalledWith("/(drawer)/sign-confirm");
  expect(takeHandoff("sign")).toEqual(expect.objectContaining({ capture_id: 9, return_to_queue: true,
    place: { name: "Bakery", city: "Augsburg" } }));
});
