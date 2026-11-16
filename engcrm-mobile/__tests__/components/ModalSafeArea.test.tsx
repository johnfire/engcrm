import { render } from "@testing-library/react-native";
import { Text } from "react-native";

jest.mock("../../i18n/I18nContext", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { ModalSafeArea } from "../../components/ModalSafeArea";
import { ClassifySheet } from "../../components/ClassifySheet";
import { RejectSheet } from "../../components/RejectSheet";

// A Modal is its own Android window drawn edge-to-edge, so the screen's padding
// does not reach it: each modal must keep its own buttons off the system bars.
describe("ModalSafeArea", () => {
  it("pads only the edges it is given and renders its children", () => {
    const { getByTestId, getByText } = render(
      <ModalSafeArea edges={["bottom"]}>
        <Text>inside</Text>
      </ModalSafeArea>,
    );
    expect(getByText("inside")).toBeTruthy();
    expect(getByTestId("modal-safe-area").props.edges).toEqual({ bottom: "additive", top: "off", left: "off", right: "off" });
  });

  it("keeps the classify sheet's buttons above the navigation bar", () => {
    const { getByTestId } = render(<ClassifySheet visible onSelect={jest.fn()} onCancel={jest.fn()} />);
    expect(getByTestId("modal-safe-area").props.edges).toEqual({ bottom: "additive", top: "off", left: "off", right: "off" });
  });

  it("keeps the reject sheet's buttons above the navigation bar", () => {
    const { getByTestId } = render(
      <RejectSheet visible venueName="Café" onConfirm={jest.fn()} onCancel={jest.fn()} />,
    );
    expect(getByTestId("modal-safe-area").props.edges).toEqual({ bottom: "additive", top: "off", left: "off", right: "off" });
  });
});
