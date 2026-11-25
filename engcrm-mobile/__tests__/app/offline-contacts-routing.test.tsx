import { render } from "@testing-library/react-native";
import { Text as MockText } from "react-native";

import ContactsScreen from "../../app/(drawer)/contacts";
import { useOffline } from "../../services/offline-context";

jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../components/local-contacts-screen", () => ({ LocalContactsScreen: () => <MockText>Local contacts</MockText> }));

it("routes Contacts to local storage when the offline feature is enabled", () => {
  jest.mocked(useOffline).mockReturnValue({ state: "opening", session: null, status: null,
    requestSync: jest.fn(), refreshStatus: jest.fn(), retryOpen: jest.fn() });
  expect(render(<ContactsScreen />).getByText("Local contacts")).toBeTruthy();
});
