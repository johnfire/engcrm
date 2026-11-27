import { fireEvent, render, waitFor } from "@testing-library/react-native";

const mockSetNextStep = jest.fn();
jest.mock("../../services/api", () => ({
  setPersonNextStep: (...a: any[]) => mockSetNextStep(...a),
}));

import { PersonNextStep } from "../../components/PersonNextStep";
import { dateInDays } from "../../services/followUps";
import { onChanged, personKey } from "../../services/refreshBus";

function setup(props: Partial<React.ComponentProps<typeof PersonNextStep>> = {}) {
  const onSaved = jest.fn();
  const screen = render(
    <PersonNextStep personId={7} step={null} date={null} canEdit onSaved={onSaved} {...props} />,
  );
  return { screen, onSaved };
}

describe("PersonNextStep", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows the step and flags an overdue date", () => {
    const { screen } = setup({ step: "Invite to coffee", date: "2020-01-31" });
    expect(screen.getByText("Invite to coffee")).toBeTruthy();
    expect(screen.getByText("by 31.01.2020 · overdue")).toBeTruthy();
  });

  it("says when nothing is planned, and a spectator gets no buttons", () => {
    const { screen } = setup({ canEdit: false });
    expect(screen.getByText("Nothing planned yet")).toBeTruthy();
    expect(screen.queryByText("Add next step")).toBeNull();
  });

  it("adds a step with a quick date, then tells the log to reload", async () => {
    const changed = jest.fn();
    const off = onChanged(personKey(7), changed);
    mockSetNextStep.mockResolvedValue({ next_step: "Call", next_step_date: dateInDays(7), logged: true });
    const { screen, onSaved } = setup();

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Call");
    fireEvent.press(screen.getByLabelText("1 week"));
    fireEvent.press(screen.getByLabelText("Check-in"));
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("Call", dateInDays(7)));
    expect(mockSetNextStep).toHaveBeenCalledWith(7, "Call", dateInDays(7), "check_in");
    expect(changed).toHaveBeenCalledTimes(1);
    off();
  });

  it("adds beside the step shown, carrying neither its words nor its day over", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: "Call", next_step_date: "2026-11-01", logged: true });
    const { screen } = setup({ step: "Call", date: "2026-11-01" });

    expect(screen.queryByText("Change")).toBeNull();
    fireEvent.press(screen.getByText("Add next step"));
    expect(screen.getByLabelText("What happens next").props.value).toBe("");
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Send quote");
    fireEvent.press(screen.getByLabelText("Commitment"));
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(mockSetNextStep).toHaveBeenCalledWith(7, "Send quote", null, "commitment"));
  });

  it("lists every open follow-up and marks only the first as done", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: "Send quote", next_step_date: null, logged: true });
    const { screen } = setup({ step: "Meet", date: "2020-01-31", followUps: [
      { id: 1, task_text: "Meet", task_type: "commitment", due_date: "2020-01-31" },
      { id: 2, task_text: "Send quote", task_type: "check_in", due_date: null },
    ] });

    expect(screen.getByText("Meet")).toBeTruthy();
    expect(screen.getByText("Send quote")).toBeTruthy();
    expect(screen.getByText("Commitment · by 31.01.2020 · overdue")).toBeTruthy();
    expect(screen.getByText("Check-in")).toBeTruthy();
    expect(screen.getAllByText("✓ Done")).toHaveLength(1);
    fireEvent.press(screen.getByText("✓ Done"));
    await waitFor(() => expect(mockSetNextStep).toHaveBeenCalledWith(7, null, null));
  });

  it("offers no Done where it cannot tell what it would complete", () => {
    const { screen } = setup({ step: "Call", date: null, canComplete: false });
    expect(screen.queryByText("✓ Done")).toBeNull();
    expect(screen.getByText("Add next step")).toBeTruthy();
  });

  it("Done clears the step", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: null, next_step_date: null, logged: true });
    const { screen, onSaved } = setup({ step: "Call", date: "2026-11-01" });

    fireEvent.press(screen.getByText("✓ Done"));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(null, null));
    expect(mockSetNextStep).toHaveBeenCalledWith(7, null, null);
  });

  it("asks for Commitment or Check-in before it saves a step, and again for the next one", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: "Call", next_step_date: null, logged: true });
    const { screen, onSaved } = setup();

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Call");
    fireEvent.press(screen.getByText("Save"));
    expect(screen.getByText("Choose Commitment or Check-in for the follow-up.")).toBeTruthy();
    expect(mockSetNextStep).not.toHaveBeenCalled();

    fireEvent.press(screen.getByLabelText("Commitment"));
    expect(screen.queryByText("Choose Commitment or Check-in for the follow-up.")).toBeNull();
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mockSetNextStep).toHaveBeenCalledWith(7, "Call", null, "commitment");

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Write");
    expect(screen.getByLabelText("Commitment").props.accessibilityState.selected).toBe(false);
  });

  it("saving without words does nothing: only Done completes a step", () => {
    const { screen, onSaved } = setup({ step: "Call", date: "2026-11-01" });

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "  ");
    fireEvent.press(screen.getByText("Save"));

    expect(mockSetNextStep).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("says so when saving fails, and keeps the editor open", async () => {
    mockSetNextStep.mockRejectedValue(new Error("offline"));
    const { screen, onSaved } = setup();

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Call");
    fireEvent.press(screen.getByLabelText("Check-in"));
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(screen.getByText("Couldn't save the next step. Try again.")).toBeTruthy());
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByLabelText("What happens next")).toBeTruthy();
  });
});
