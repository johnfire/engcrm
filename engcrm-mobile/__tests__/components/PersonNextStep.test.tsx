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
    expect(screen.getByText("by 2020-01-31 · overdue")).toBeTruthy();
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
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("Call", dateInDays(7)));
    expect(mockSetNextStep).toHaveBeenCalledWith(7, "Call", dateInDays(7));
    expect(changed).toHaveBeenCalledTimes(1);
    off();
  });

  it("changing the words keeps the date unless another is picked", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: "Call again", next_step_date: "2026-11-01", logged: true });
    const { screen } = setup({ step: "Call", date: "2026-11-01" });

    fireEvent.press(screen.getByText("Change"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Call again");
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(mockSetNextStep).toHaveBeenCalledWith(7, "Call again", "2026-11-01"));
  });

  it("Done clears the step", async () => {
    mockSetNextStep.mockResolvedValue({ next_step: null, next_step_date: null, logged: true });
    const { screen, onSaved } = setup({ step: "Call", date: "2026-11-01" });

    fireEvent.press(screen.getByText("✓ Done"));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(null, null));
    expect(mockSetNextStep).toHaveBeenCalledWith(7, null, null);
  });

  it("says so when saving fails, and keeps the editor open", async () => {
    mockSetNextStep.mockRejectedValue(new Error("offline"));
    const { screen, onSaved } = setup();

    fireEvent.press(screen.getByText("Add next step"));
    fireEvent.changeText(screen.getByLabelText("What happens next"), "Call");
    fireEvent.press(screen.getByText("Save"));

    await waitFor(() => expect(screen.getByText("Couldn't save the next step. Try again.")).toBeTruthy());
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByLabelText("What happens next")).toBeTruthy();
  });
});
