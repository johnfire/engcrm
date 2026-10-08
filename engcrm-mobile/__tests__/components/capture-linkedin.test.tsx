import { act, fireEvent, render } from "@testing-library/react-native";
import { CaptureLinkedIn } from "../../components/capture-linkedin";
import { searchCaptureProfiles } from "../../services/capture-linkedin";

jest.mock("../../services/capture-linkedin", () => ({ searchCaptureProfiles: jest.fn() }));
const mockSearch = searchCaptureProfiles as jest.Mock;
const profile = { url: "https://www.linkedin.com/in/anna-roth", title: "Anna Roth - ACME", snippet: "Augsburg" };
const props = { captureId: 7, name: "Anna Roth", company: "ACME", city: "Augsburg", onChange: jest.fn(), disabled: false };

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockSearch.mockResolvedValue({ status: "found", candidates: [profile] });
});
afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); });

async function finishSearch() {
  await act(async () => { jest.advanceTimersByTime(650); });
}

it("automatically searches but saves nothing until the profile is selected", async () => {
  const { getByText } = render(<CaptureLinkedIn {...props} />);
  await finishSearch();
  expect(mockSearch).toHaveBeenCalledWith(7, "Anna Roth", "ACME", "Augsburg");
  expect(props.onChange).not.toHaveBeenCalled();
  fireEvent.press(getByText("Use this profile"));
  expect(props.onChange).toHaveBeenCalledWith(profile.url);
});

it("lets the user paste or remove a profile", () => {
  const { getByDisplayValue } = render(<CaptureLinkedIn {...props} value={profile.url} />);
  fireEvent.changeText(getByDisplayValue(profile.url), "");
  expect(props.onChange).toHaveBeenCalledWith("");
});

it("shows a nonblocking error and lets the user retry", async () => {
  mockSearch.mockRejectedValueOnce(new Error("offline"));
  const { getByText } = render(<CaptureLinkedIn {...props} />);
  await finishSearch();
  expect(getByText("LinkedIn search is unavailable. Retry, paste a link, or save without one.")).toBeTruthy();
  fireEvent.press(getByText("Search again"));
  await finishSearch();
  expect(getByText(profile.title)).toBeTruthy();
});

it("does not search a company-only scan", async () => {
  const { getByText } = render(<CaptureLinkedIn {...props} name="" />);
  await finishSearch();
  expect(mockSearch).not.toHaveBeenCalled();
  expect(getByText("Enter the person’s full name to look for a profile.")).toBeTruthy();
});

it("discards an old lookup response when the scanned identity changes", async () => {
  let resolveOld!: (response: unknown) => void;
  mockSearch.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }));
  const { rerender, queryByText, getByText } = render(<CaptureLinkedIn {...props} />);
  await finishSearch();
  const nextProfile = { ...profile, title: "Bernd Klein", url: "https://www.linkedin.com/in/bernd-klein" };
  mockSearch.mockResolvedValueOnce({ status: "found", candidates: [nextProfile] });
  rerender(<CaptureLinkedIn {...props} name="Bernd Klein" />);
  await finishSearch();
  await act(async () => { resolveOld({ status: "found", candidates: [profile] }); });
  expect(getByText(nextProfile.title)).toBeTruthy();
  expect(queryByText(profile.title)).toBeNull();
});

it("disables profile selection while the contact is being saved", async () => {
  const { getByText } = render(<CaptureLinkedIn {...props} disabled />);
  await finishSearch();
  fireEvent.press(getByText("Use this profile"));
  expect(props.onChange).not.toHaveBeenCalled();
});
