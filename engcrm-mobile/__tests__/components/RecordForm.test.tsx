import { fireEvent, render } from "@testing-library/react-native";

import { changedFields, fieldProblem, RecordForm } from "../../components/RecordForm";
import { ORGANIZATION_FIELDS, PERSON_FIELDS } from "../../services/recordFields";

const FIELDS = ORGANIZATION_FIELDS;

describe("changedFields", () => {
  it("returns only trimmed values that differ from the baseline", () => {
    const changed = changedFields(
      FIELDS,
      { name: " Acme ", city: "Ulm", phone: "123 " },
      { name: "Acme", city: "Bonn", phone: "123" },
    );
    expect(changed).toEqual({ city: "Ulm" });
  });

  it("treats a missing value and a blank one as the same, and reports a cleared field as blank", () => {
    expect(changedFields(FIELDS, { name: "A", city: "  " }, { name: "A" })).toEqual({});
    expect(changedFields(FIELDS, { name: "A", city: "" }, { name: "A", city: "Ulm" })).toEqual({ city: "" });
  });
});

describe("fieldProblem", () => {
  const field = (key: string) => FIELDS.find((f) => f.key === key)!;
  it("requires the name", () => {
    expect(fieldProblem(field("name"), "  ")).toBe("recordForm.required");
    expect(fieldProblem(field("name"), "Acme")).toBeNull();
  });
  it("accepts a blank optional field but checks a country and an email when given", () => {
    expect(fieldProblem(field("country"), "")).toBeNull();
    expect(fieldProblem(field("country"), "de")).toBeNull();
    expect(fieldProblem(field("country"), "Germany")).toBe("recordForm.countryInvalid");
    expect(fieldProblem(field("country"), "D1")).toBe("recordForm.countryInvalid");
    expect(fieldProblem(field("email"), "a@b.de")).toBeNull();
    expect(fieldProblem(field("email"), "nope")).toBe("recordForm.emailInvalid");
    expect(fieldProblem(field("email"), "a b@c.de")).toBe("recordForm.emailInvalid");
  });
});

describe("the field lists", () => {
  it("each list has a required name and no repeated field", () => {
    for (const list of [ORGANIZATION_FIELDS, PERSON_FIELDS]) {
      expect(list[0]).toMatchObject({ key: "name", required: true });
      expect(new Set(list.map((f) => f.key)).size).toBe(list.length);
    }
  });
});

function setup(props: Partial<React.ComponentProps<typeof RecordForm>> = {}) {
  const onSubmit = jest.fn();
  const screen = render(
    <RecordForm
      fields={FIELDS}
      baseline={{ name: "Acme", city: "Ulm", country: "Germany" }}
      saving={false}
      submitLabel="Save changes"
      onSubmit={onSubmit}
      {...props}
    />,
  );
  return { screen, onSubmit };
}

describe("RecordForm", () => {
  it("cannot be saved until something changes", () => {
    const { screen, onSubmit } = setup();
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("button").props.accessibilityState.disabled).toBe(true);
  });

  it("sends only the fields that changed", () => {
    const { screen, onSubmit } = setup();
    fireEvent.changeText(screen.getByLabelText("Phone"), " 0731 1 ");
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).toHaveBeenCalledWith({ phone: "0731 1" });
  });

  it("an untouched legacy value does not block an unrelated edit", () => {
    const { screen, onSubmit } = setup(); // country is "Germany" — not a 2-letter code
    fireEvent.changeText(screen.getByLabelText("Phone"), "1");
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).toHaveBeenCalledWith({ phone: "1" });
  });

  it("refuses a bad value with a message, and clears the message when it is edited", () => {
    const { screen, onSubmit } = setup();
    fireEvent.changeText(screen.getByLabelText("Country (2 letters)"), "XYZ".slice(0, 2) + "1");
    fireEvent.changeText(screen.getByLabelText("Email"), "nope");
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("That email address doesn't look right")).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText("Email"), "a@b.de");
    expect(screen.queryByText("That email address doesn't look right")).toBeNull();
  });

  it("will not save a blank name", () => {
    const { screen, onSubmit } = setup();
    fireEvent.changeText(screen.getByLabelText("Name"), "   ");
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Required")).toBeTruthy();
  });

  it("a name carried over from Search counts as typed, so a new record can be added at once", () => {
    const { screen, onSubmit } = setup({ baseline: {}, start: { name: "Acme Neu" }, submitLabel: "Add organization" });
    expect(screen.getByDisplayValue("Acme Neu")).toBeTruthy();
    fireEvent.press(screen.getByText("Add organization"));
    expect(onSubmit).toHaveBeenCalledWith({ name: "Acme Neu" });
  });

  it("extra changes outside the text fields (a switch) allow saving on their own", () => {
    const { screen, onSubmit } = setup({ extraChange: true });
    fireEvent.press(screen.getByText("Save changes"));
    expect(onSubmit).toHaveBeenCalledWith({});
  });

  it("shows the server's error and locks while saving", () => {
    const { screen } = setup({ error: "Server said no", saving: true });
    expect(screen.getByText("Server said no")).toBeTruthy();
    expect(screen.getByLabelText("Name").props.editable).toBe(false);
  });
});
