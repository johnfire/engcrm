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

  it("shows no Save button until something changes", () => {
    const { screen } = setup();
    expect(screen.queryByText("Save")).toBeNull();
  });

  it("moving to a new stage also picks the status that normally goes with it — two taps", async () => {
    const { screen, onSave } = setup("candidate", "none");
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ pipeline_stage: "suspect", status: "ready" }));
  });

  it("keeps the status when it still fits the new stage, and sends only what changed", async () => {
    const { screen, onSave } = setup("prospect", "contacted");
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ pipeline_stage: "suspect" }));
  });

  it("can change the status alone", async () => {
    const { screen, onSave } = setup("opportunity", "meeting");
    fireEvent.press(screen.getByLabelText("Proposal"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ status: "proposal" }));
  });

  it("marks an unusual pairing but still lets you save it", async () => {
    const { screen, onSave } = setup("customer", "none");
    expect(screen.queryByText(/unusual combination/i)).toBeNull();
    fireEvent.press(screen.getByLabelText("Proposal"));
    expect(screen.getByText(/unusual combination/i)).toBeTruthy();
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ status: "proposal" }));
  });

  it("hides Save again after a successful save and treats the new values as current", async () => {
    const { screen, onSave } = setup("candidate", "none");
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(screen.queryByText("Save")).toBeNull());
    fireEvent.press(screen.getByLabelText("Contacted"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith({ status: "contacted" }));
  });

  it("reverts and says so when saving fails", async () => {
    const onSave = jest.fn().mockRejectedValue(new Error("offline"));
    const { screen } = setup("candidate", "none", onSave);
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(screen.getByText(/Couldn't save/)).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText("Suspect").props.accessibilityState.selected).toBe(false);
    expect(screen.queryByText("Save")).toBeNull(); // nothing pending any more
  });

  it("cannot be tapped twice while saving", async () => {
    let finish: () => void = () => {};
    const onSave = jest.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const { screen } = setup("candidate", "none", onSave);
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save"));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Customer").props.accessibilityState.disabled).toBe(true);
    finish();
    await waitFor(() => expect(screen.queryByText("Save")).toBeNull());
  });
});
