import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { SavedMessageLibrary } from "../../components/saved-message-library";
import { copyMessage, fetchSavedMessages, saveMessage } from "../../services/saved-messages";
import { openWebsite } from "../../services/webLinks";

jest.mock("../../services/saved-messages", () => ({ fetchSavedMessages: jest.fn(), saveMessage: jest.fn(), copyMessage: jest.fn() }));
jest.mock("../../services/webLinks", () => ({ openWebsite: jest.fn() }));
const BODY = "  α\r\n\n🙂\t  ";
const MESSAGE = { id: 7, title: "label", body: BODY, version: 1, created_at: "2026-10-08", updated_at: "2026-10-08" };
const PROFILE = "https://www.linkedin.com/in/test-profile";

beforeEach(() => {
  jest.restoreAllMocks();
  jest.clearAllMocks();
  (fetchSavedMessages as jest.Mock).mockResolvedValue([]);
  (saveMessage as jest.Mock).mockResolvedValue(MESSAGE);
  (copyMessage as jest.Mock).mockResolvedValue(undefined);
  (openWebsite as jest.Mock).mockResolvedValue(true);
});

it("starts empty and lets the user add, preview, copy and edit exact wording", async () => {
  const screen = render(<SavedMessageLibrary profile={PROFILE} />);
  await waitFor(() => expect(screen.getByText("No saved messages yet. Add a message you wrote.")).toBeTruthy());
  fireEvent.press(screen.getByText("Add a message"));
  expect(screen.getByLabelText("Your exact wording").props.value).toBe("");
  fireEvent.changeText(screen.getByLabelText("Message label"), "label");
  fireEvent.changeText(screen.getByLabelText("Your exact wording"), BODY);
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText("Copy message")).toBeTruthy());
  expect(saveMessage).toHaveBeenCalledWith({ title: "label", body: BODY }, undefined);
  fireEvent.press(screen.getByText("Copy message"));
  await waitFor(() => expect(copyMessage).toHaveBeenCalledWith(BODY));
  expect(openWebsite).not.toHaveBeenCalled();
  fireEvent.press(screen.getByText("Open contact on LinkedIn"));
  await waitFor(() => expect(openWebsite).toHaveBeenCalledWith(PROFILE));
  fireEvent.press(screen.getByText("Edit saved message"));
  expect(screen.getByLabelText("Your exact wording").props.value).toBe(BODY);
  const edited = BODY + "\n";
  (saveMessage as jest.Mock).mockResolvedValue({ ...MESSAGE, body: edited, version: 2 });
  fireEvent.changeText(screen.getByLabelText("Your exact wording"), edited);
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText("Copy message")).toBeTruthy());
  expect(saveMessage).toHaveBeenLastCalledWith({ title: "label", body: edited }, MESSAGE);
  fireEvent.press(screen.getByText("Copy message"));
  await waitFor(() => expect(copyMessage).toHaveBeenLastCalledWith(edited));
});

it("chooses a stored message without copying or opening LinkedIn automatically", async () => {
  (fetchSavedMessages as jest.Mock).mockResolvedValue([MESSAGE]);
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("label")).toBeTruthy());
  fireEvent.press(screen.getByText("label"));
  expect(screen.getByText("Copy message")).toBeTruthy();
  expect(screen.queryByText("Open contact on LinkedIn")).toBeNull();
  expect(copyMessage).not.toHaveBeenCalled();
});

it("preserves unsaved wording when a save fails and allows retry", async () => {
  (saveMessage as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("Add a message")).toBeTruthy());
  fireEvent.press(screen.getByText("Add a message"));
  fireEvent.changeText(screen.getByLabelText("Message label"), "label");
  fireEvent.changeText(screen.getByLabelText("Your exact wording"), BODY);
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText("Could not save. Your wording is still here; please try again.")).toBeTruthy());
  expect(screen.getByLabelText("Your exact wording").props.value).toBe(BODY);
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText("Copy message")).toBeTruthy());
});

it("retains edits on a version conflict", async () => {
  (fetchSavedMessages as jest.Mock).mockResolvedValue([MESSAGE]);
  (saveMessage as jest.Mock).mockRejectedValue({ response: { status: 409 } });
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("label")).toBeTruthy());
  fireEvent.press(screen.getByText("label"));
  fireEvent.press(screen.getByText("Edit saved message"));
  fireEvent.changeText(screen.getByLabelText("Your exact wording"), BODY + "\n");
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText(/This message changed on another device/)).toBeTruthy());
  expect(screen.getByLabelText("Your exact wording").props.value).toBe(BODY + "\n");
});

it("reports a failed copy without opening LinkedIn", async () => {
  (fetchSavedMessages as jest.Mock).mockResolvedValue([MESSAGE]);
  (copyMessage as jest.Mock).mockRejectedValue(new Error("unavailable"));
  const screen = render(<SavedMessageLibrary profile={PROFILE} />);
  await waitFor(() => expect(screen.getByText("label")).toBeTruthy());
  fireEvent.press(screen.getByText("label"));
  fireEvent.press(screen.getByText("Copy message"));
  await waitFor(() => expect(screen.getByText("Could not copy the message. Please try again.")).toBeTruthy());
  expect(openWebsite).not.toHaveBeenCalled();
});

it("asks before discarding unsaved edits", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("Add a message")).toBeTruthy());
  fireEvent.press(screen.getByText("Add a message"));
  fireEvent.changeText(screen.getByLabelText("Your exact wording"), BODY);
  fireEvent.press(screen.getByText("Cancel"));
  expect(alert).toHaveBeenCalledWith("Discard these unsaved changes?", undefined, expect.any(Array));
  expect(screen.getByLabelText("Your exact wording").props.value).toBe(BODY);
});

it("makes library loading failures retryable", async () => {
  (fetchSavedMessages as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("Could not load your messages. Please try again.")).toBeTruthy());
  fireEvent.press(screen.getByText("Try again"));
  await waitFor(() => expect(screen.getByText("Add a message")).toBeTruthy());
});

it("refreshes changes from another device and clears the old preview", async () => {
  (fetchSavedMessages as jest.Mock).mockResolvedValueOnce([MESSAGE]);
  const screen = render(<SavedMessageLibrary />);
  await waitFor(() => expect(screen.getByText("label")).toBeTruthy());
  fireEvent.press(screen.getByText("label"));
  (fetchSavedMessages as jest.Mock).mockResolvedValueOnce([{ ...MESSAGE, title: "updated label", version: 2 }]);
  fireEvent.press(screen.getByText("Refresh messages"));
  await waitFor(() => expect(screen.getByText("updated label")).toBeTruthy());
  expect(screen.queryByText("Copy message")).toBeNull();
  expect(fetchSavedMessages).toHaveBeenCalledTimes(2);
});
