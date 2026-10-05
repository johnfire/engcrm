import { render, fireEvent, waitFor } from "@testing-library/react-native";

import { StageStatusPicker, orderedStatuses } from "../../components/StageStatusPicker";

function setup(stage = "candidate", status = "none", onSave = jest.fn().mockResolvedValue(undefined)) {
  const screen = render(<StageStatusPicker stage={stage as any} status={status as any} onSave={onSave} />);
  return { screen, onSave };
}

describe("StageStatusPicker", () => {
  it("offers every stage, and lists the statuses that normally go with the stage first", () => {
    const { screen } = setup("suspect", "ready");
    for (const label of ["Candidate", "Suspect", "Prospect", "Opportunity", "Customer", "Not in pipeline"]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    // 6 stage chips, then the statuses: suspect's usual ones lead.
    const labels = screen.getAllByRole("radio").map((chip) => chip.props.accessibilityLabel);
    expect(labels.slice(6, 10)).toEqual(["Ready to contact", "Contacted", "Dormant", "On hold"]);
    expect(orderedStatuses("suspect").slice(0, 4)).toEqual(["ready", "contacted", "dormant", "on_hold"]);
  });

  it("has no Save button: there is nothing to save until a chip is tapped", () => {
    const { screen, onSave } = setup();
    expect(screen.queryByText("Save")).toBeNull();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("tapping a new stage saves at once, with the status that normally goes with it", async () => {
    const { screen, onSave } = setup("candidate", "none");
    fireEvent.press(screen.getByLabelText("Suspect"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ pipeline_stage: "suspect", status: "ready" }));
    await waitFor(() => expect(screen.getByText("Saved ✓")).toBeTruthy());
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("keeps the status when it still fits the new stage, and sends only what changed", async () => {
    const { screen, onSave } = setup("prospect", "contacted");
    fireEvent.press(screen.getByLabelText("Suspect"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ pipeline_stage: "suspect" }));
  });

  it("tapping a status alone saves just the status", async () => {
    const { screen, onSave } = setup("opportunity", "meeting");
    fireEvent.press(screen.getByLabelText("Proposal"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ status: "proposal" }));
  });

  it("tapping what is already selected saves nothing", () => {
    const { screen, onSave } = setup("opportunity", "meeting");
    fireEvent.press(screen.getByLabelText("Opportunity"));
    fireEvent.press(screen.getByLabelText("Meeting"));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("marks an unusual pairing and still saves it", async () => {
    const { screen, onSave } = setup("customer", "none");
    expect(screen.queryByText(/unusual combination/i)).toBeNull();
    fireEvent.press(screen.getByLabelText("Proposal"));
    expect(screen.getByText(/unusual combination/i)).toBeTruthy();
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ status: "proposal" }));
  });

  it("treats what was saved as current: the next tap sends only its own change", async () => {
    const { screen, onSave } = setup("candidate", "none");
    fireEvent.press(screen.getByLabelText("Suspect"));
    await waitFor(() => expect(screen.getByText("Saved ✓")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Contacted"));
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith({ status: "contacted" }));
  });

  it("reverts and says so when saving fails", async () => {
    const onSave = jest.fn().mockRejectedValue(new Error("offline"));
    const { screen } = setup("candidate", "none", onSave);
    fireEvent.press(screen.getByLabelText("Suspect"));
    await waitFor(() => expect(screen.getByText(/Couldn't save/)).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText("Suspect").props.accessibilityState.selected).toBe(false);
    expect(screen.queryByText("Saved ✓")).toBeNull();
  });

  it("cannot be tapped again while a save is running", async () => {
    let finish: () => void = () => {};
    const onSave = jest.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const { screen } = setup("candidate", "none", onSave);
    fireEvent.press(screen.getByLabelText("Suspect"));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Saving…")).toBeTruthy();
    expect(screen.getByLabelText("Customer").props.accessibilityState.disabled).toBe(true);
    finish();
    await waitFor(() => expect(screen.getByText("Saved ✓")).toBeTruthy());
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});

describe("StageStatusPicker embedded", () => {
  it("reports the pending change instead of saving, and clears it when put back", () => {
    const onChange = jest.fn();
    const onSave = jest.fn();
    const screen = render(
      <StageStatusPicker stage="candidate" status="none" onSave={onSave} embedded onChange={onChange} />,
    );
    expect(screen.queryByText("Save")).toBeNull();
    fireEvent.press(screen.getByLabelText("Suspect"));
    expect(onChange).toHaveBeenLastCalledWith({ pipeline_stage: "suspect", status: "ready" });
    expect(screen.queryByText("Save")).toBeNull();
    fireEvent.press(screen.getByLabelText("Candidate"));
    fireEvent.press(screen.getByLabelText("—"));
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(onSave).not.toHaveBeenCalled();
  });
});
