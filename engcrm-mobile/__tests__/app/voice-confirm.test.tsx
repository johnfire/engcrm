import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { useEffect as mockUseEffect } from "react";

const mockConfirmVoice = jest.fn();
jest.mock("../../services/api", () => ({ confirmVoice: (...args: unknown[]) => mockConfirmVoice(...args) }));
jest.mock("../../services/handoff", () => ({
  takeHandoff: () => ({ summary: "Met Anna", follow_up_text: "Send details", candidates: [{ id: 9, name: "Acme" }] }),
}));
jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: jest.fn() }),
  useFocusEffect: (callback: () => void) => mockUseEffect(callback, [callback]),
}));

import VoiceConfirmScreen from "../../app/(drawer)/voice-confirm";

it("sends the chosen type with a voice follow-up", async () => {
  mockConfirmVoice.mockResolvedValue({ contact_id: 9 });
  const screen = render(<VoiceConfirmScreen />);
  await screen.findByDisplayValue("Send details");
  fireEvent.press(screen.getByLabelText("Check-in"));
  fireEvent.press(screen.getByText("Save"));
  await waitFor(() => expect(mockConfirmVoice).toHaveBeenCalledWith(
    expect.objectContaining({ follow_up_text: "Send details", follow_up_type: "check_in" }),
  ));
});
