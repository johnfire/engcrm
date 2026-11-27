import { Alert } from "react-native";
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

it("asks for the type before it saves a voice follow-up", async () => {
  mockConfirmVoice.mockClear();
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = render(<VoiceConfirmScreen />);
  await screen.findByDisplayValue("Send details");
  expect(screen.queryByText(/review queue/)).toBeNull();
  fireEvent.press(screen.getByText("Save"));
  expect(alert).toHaveBeenCalledWith("Follow-up type", "Choose Commitment or Check-in for the follow-up.");
  expect(mockConfirmVoice).not.toHaveBeenCalled();
  alert.mockRestore();
});

it("needs no type once there is no follow-up action", async () => {
  mockConfirmVoice.mockClear();
  mockConfirmVoice.mockResolvedValue({ contact_id: 9 });
  const screen = render(<VoiceConfirmScreen />);
  fireEvent.changeText(await screen.findByDisplayValue("Send details"), "");
  fireEvent.press(screen.getByText("Save"));
  await waitFor(() => expect(mockConfirmVoice).toHaveBeenCalled());
  expect(mockConfirmVoice.mock.calls[0][0]).not.toHaveProperty("follow_up_type");
});
