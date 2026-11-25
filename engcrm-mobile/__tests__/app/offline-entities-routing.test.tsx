import { render } from "@testing-library/react-native";
import { Text as MockText } from "react-native";

import OrganizationsScreen from "../../app/(drawer)/organizations";
import PeopleScreen from "../../app/(drawer)/people";
import { useOffline } from "../../services/offline-context";

jest.mock("../../services/offline-context", () => ({ useOffline: jest.fn() }));
jest.mock("../../components/local-entities-screen", () => ({ LocalEntitiesScreen: ({ kind }: { kind: string }) => <MockText>{kind}</MockText> }));

it("routes Organizations and People to local lists when offline mode is enabled", () => {
  jest.mocked(useOffline).mockReturnValue({ state: "opening", session: null, status: null,
    requestSync: jest.fn(), refreshStatus: jest.fn(), retryOpen: jest.fn() });
  expect(render(<OrganizationsScreen />).getByText("organization")).toBeTruthy();
  expect(render(<PeopleScreen />).getByText("person")).toBeTruthy();
});
