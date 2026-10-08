import { act, render, waitFor } from "@testing-library/react-native";
import { Text as MockText } from "react-native";

let mockContactId = "7";
const mockFetchPerson = jest.fn();
jest.mock("expo-router", () => ({ useLocalSearchParams: () => ({ id: mockContactId }) }));
jest.mock("../../services/api", () => ({ fetchPerson: (...args: unknown[]) => mockFetchPerson(...args) }));
jest.mock("../../components/saved-message-library", () => ({
  SavedMessageLibrary: ({ profile }: { profile?: string }) => <MockText testID="library-profile">{profile || "none"}</MockText>,
}));
import SavedMessagesScreen from "../../app/(drawer)/saved-messages";

beforeEach(() => { mockContactId = "7"; mockFetchPerson.mockReset(); });

it("loads the chosen contact and passes its stored LinkedIn profile to the picker", async () => {
  const profile = "https://www.linkedin.com/in/contact-seven";
  mockFetchPerson.mockResolvedValue({ id: 7, name: "Contact 7", linkedin_url: profile });
  const screen = render(<SavedMessagesScreen />);
  await waitFor(() => expect(screen.getByText("Contact 7")).toBeTruthy());
  expect(mockFetchPerson).toHaveBeenCalledWith(7);
  expect(screen.getByTestId("library-profile").props.children).toBe(profile);
});

it("never exposes the previous contact's profile while loading a different contact", async () => {
  mockFetchPerson.mockResolvedValueOnce({ id: 7, name: "Contact 7", linkedin_url: "profile-seven" });
  const screen = render(<SavedMessagesScreen />);
  await waitFor(() => expect(screen.getByText("Contact 7")).toBeTruthy());
  let resolveContact!: (person: unknown) => void;
  mockFetchPerson.mockReturnValueOnce(new Promise((resolve) => { resolveContact = resolve; }));
  mockContactId = "8";
  screen.rerender(<SavedMessagesScreen />);
  expect(screen.getByTestId("library-profile").props.children).toBe("none");
  await act(async () => { resolveContact({ id: 8, name: "Contact 8", linkedin_url: "profile-eight" }); });
  expect(screen.getByTestId("library-profile").props.children).toBe("profile-eight");
});

it("keeps the library available when the contact cannot be loaded", async () => {
  mockFetchPerson.mockRejectedValue(new Error("offline"));
  const screen = render(<SavedMessagesScreen />);
  await waitFor(() => expect(screen.getByText("Contact details could not be loaded. You can still copy a message.")).toBeTruthy());
  expect(screen.getByTestId("library-profile").props.children).toBe("none");
});
