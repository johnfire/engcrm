import { render, fireEvent, waitFor } from "@testing-library/react-native";

import { PersonStagePicker } from "../../components/PersonStagePicker";

function setup(stage: any = "candidate", onSave = jest.fn().mockResolvedValue(undefined), organizationStage?: any) {
  const screen = render(<PersonStagePicker stage={stage} onSave={onSave} organizationStage={organizationStage} />);
  return { screen, onSave };
}

describe("PersonStagePicker", () => {
  it("shows the current stage as selected", () => {
    const { screen } = setup("prospect");
    expect(screen.getByLabelText("Prospect").props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(false);
  });

  it("one tap saves the new stage", async () => {
    const { screen, onSave } = setup("candidate");
    fireEvent.press(screen.getByLabelText("Customer"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("customer"));
    expect(screen.getByLabelText("Customer").props.accessibilityState.selected).toBe(true);
  });

  it("tapping the stage it already has does nothing", () => {
    const { screen, onSave } = setup("candidate");
    fireEvent.press(screen.getByLabelText("Candidate"));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("can clear the stage, but not when there is none", async () => {
    const { screen, onSave } = setup("suspect");
    fireEvent.press(screen.getByText("No stage"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(null));
    fireEvent.press(screen.getByText("No stage"));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("reverts and says so when saving fails", async () => {
    const onSave = jest.fn().mockRejectedValue(new Error("offline"));
    const { screen } = setup("candidate", onSave);
    fireEvent.press(screen.getByLabelText("Customer"));
    await waitFor(() => expect(screen.getByText(/Couldn't save the stage/)).toBeTruthy());
    expect(screen.getByLabelText("Candidate").props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText("Customer").props.accessibilityState.selected).toBe(false);
  });

  it("shows the organization's own stage beside it, when linked", () => {
    const { screen } = setup("candidate", undefined, "suspect");
    expect(screen.getByText("Their organization: Suspect")).toBeTruthy();
  });

  it("says nothing about an organization when there is none", () => {
    const { screen } = setup("candidate");
    expect(screen.queryByText(/Their organization/)).toBeNull();
  });
});
