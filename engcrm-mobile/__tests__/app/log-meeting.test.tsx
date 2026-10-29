import { Alert } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

const store: Record<string, string> = {};
jest.mock("@react-native-async-storage/async-storage", () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (k: string) => (k in store ? store[k] : null)),
    setItem: jest.fn(async (k: string, v: string) => { store[k] = v; }),
    removeItem: jest.fn(async (k: string) => { delete store[k]; }),
  },
}));

const mockAddOrgNote = jest.fn();
const mockAddPersonNote = jest.fn();
const mockFetchOrg = jest.fn();
const mockFetchPerson = jest.fn();
const mockTranscribeOrg = jest.fn();
const mockTranscribePerson = jest.fn();
const mockSetNextStep = jest.fn();
jest.mock("../../services/api", () => ({
  setPersonNextStep: (...a: any[]) => mockSetNextStep(...a),
  addOrganizationNote: (...a: any[]) => mockAddOrgNote(...a),
  addPersonNote: (...a: any[]) => mockAddPersonNote(...a),
  fetchOrganization: (...a: any[]) => mockFetchOrg(...a),
  fetchPerson: (...a: any[]) => mockFetchPerson(...a),
  transcribeOrganizationNote: (...a: any[]) => mockTranscribeOrg(...a),
  transcribePersonNote: (...a: any[]) => mockTranscribePerson(...a),
}));

// The note's offer and the deal it moves (one deal per offer pitched).
const mockFetchDeals = jest.fn();
const mockChangeDeal = jest.fn();
const mockSetDealNextStep = jest.fn();
jest.mock("../../services/deals", () => ({
  ...jest.requireActual("../../services/deals"),
  fetchOffers: () => Promise.resolve([
    { id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" },
    { id: 2, slug: "learnwohl", name: "LearnWohl", website: null, revenue_kind: "subscription" },
  ]),
  fetchDeals: (...a: any[]) => mockFetchDeals(...a),
  changeDeal: (...a: any[]) => mockChangeDeal(...a),
  setDealNextStep: (...a: any[]) => mockSetDealNextStep(...a),
}));
const deal = (id: number, owner: "organization" | "person", pipeline_stage: string, status = "none") => ({
  id, offer_id: 1, offer_slug: "consulting", offer_name: "Consulting", revenue_kind: "one_off", offer_archived: false,
  contact_id: owner === "organization" ? 42 : null, person_id: owner === "person" ? 7 : null,
  pipeline_stage, status, next_step: null, next_step_date: null, contact_person_id: null, contact_person_name: null,
});

const mockGetRole = jest.fn();
jest.mock("../../services/auth", () => ({ getRole: (...a: any[]) => mockGetRole(...a) }));

let mockParams: Record<string, string> = {};
const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockCanGoBack = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ back: mockBack, replace: mockReplace, canGoBack: mockCanGoBack }),
}));

const mockRecorder = {
  prepareToRecordAsync: jest.fn(async () => {}),
  record: jest.fn(),
  stop: jest.fn(async () => {}),
  uri: "file:///rec.m4a",
};
const mockPermission = jest.fn(async () => ({ granted: true }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => mockRecorder,
  RecordingPresets: { HIGH_QUALITY: {} },
  requestRecordingPermissionsAsync: () => mockPermission(),
  setAudioModeAsync: jest.fn(async () => {}),
}));

import LogMeetingScreen, { dateInDays, typedMinutes } from "../../app/(drawer)/log-meeting";
import { onChanged, organizationKey, personKey } from "../../services/refreshBus";

const ORG = { id: 42, name: "Acme Salon", pipeline_stage: "candidate", status: "none" };
const PERSON = { id: 7, name: "Anna Roth", pipeline_stage: "candidate", company_pipeline_stage: "suspect" };

function setup(kind: "organization" | "person" = "organization", role = "admin") {
  mockParams = kind === "organization"
    ? { kind, id: "42", name: "Acme Salon" }
    : { kind, id: "7", name: "Anna Roth" };
  mockGetRole.mockResolvedValue(role);
  mockFetchOrg.mockResolvedValue(ORG);
  mockFetchPerson.mockResolvedValue(PERSON);
  mockFetchDeals.mockImplementation(async (owner: string) =>
    owner === "organization" ? [deal(70, "organization", "candidate")] : [deal(90, "person", "candidate")]);
  return render(<LogMeetingScreen />);
}

async function typeNote(screen: ReturnType<typeof render>, text: string) {
  const box = await screen.findByLabelText("What was said, agreed, next steps…");
  fireEvent.changeText(box, text);
}

describe("log a meeting — organization", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    for (const k of Object.keys(store)) delete store[k];
    mockCanGoBack.mockReturnValue(true);
    mockAddOrgNote.mockResolvedValue({ id: 1, follow_up_date: null });
    mockChangeDeal.mockResolvedValue(deal(70, "organization", "suspect", "ready"));
  });

  it.each(["organization", "person"] as const)("logs Post mail for a %s", async (kind) => {
    mockAddPersonNote.mockResolvedValue({ id: 1 });
    const screen = setup(kind);
    await typeNote(screen, "Posted a training brochure");
    fireEvent.press(screen.getByLabelText("Post mail"));
    fireEvent.press(screen.getByText("Save note"));
    const save = kind === "organization" ? mockAddOrgNote : mockAddPersonNote;
    await waitFor(() => expect(save).toHaveBeenCalled());
    if (kind === "organization") {
      expect(save.mock.calls[0][1]).toMatchObject({ method: "letter", note: "Posted a training brochure" });
    } else {
      expect(save.mock.calls[0].slice(0, 3)).toEqual([7, "Posted a training brochure", "letter"]);
    }
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
  });

  it("saves a note, a follow-up and a stage change with one tap, then goes back", async () => {
    const changed = jest.fn();
    const off = onChanged(organizationKey(42), changed);
    const screen = setup();
    await typeNote(screen, "  Met the owner, wants a demo  ");
    fireEvent.press(screen.getByLabelText("Drop-in"));
    fireEvent.press(screen.getByLabelText("1 week"));
    fireEvent.changeText(screen.getByPlaceholderText("About (optional)"), "send quote");
    await waitFor(() => expect(screen.getByLabelText("Suspect")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save note and update stage"));

    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddOrgNote).toHaveBeenCalledWith(42, {
      note: "Met the owner, wants a demo",
      method: "in_person",
      follow_up_date: dateInDays(7),
      follow_up_text: "send quote",
      duration_minutes: null,
      offer: "consulting", // its one open deal's offer, picked for you
    });
    expect(mockChangeDeal).toHaveBeenCalledWith(70, { stage: "suspect", status: "ready" });
    // the note is sent first, so a failing stage change can never lose it
    expect(mockAddOrgNote.mock.invocationCallOrder[0]).toBeLessThan(mockChangeDeal.mock.invocationCallOrder[0]);
    expect(changed).toHaveBeenCalledTimes(1); // the screen underneath reloads
    expect(Object.keys(store)).toEqual([]); // the draft is gone
    off();
  });

  it("a note alone sends no follow-up and no stage change", async () => {
    const screen = setup();
    await typeNote(screen, "Quick call, no news");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    await waitFor(() => expect(mockAddOrgNote).toHaveBeenCalled());
    expect(mockAddOrgNote.mock.calls[0][1]).toMatchObject({
      note: "Quick call, no news", method: null, follow_up_date: null, follow_up_text: null,
      duration_minutes: null,
    });
    expect(mockChangeDeal).not.toHaveBeenCalled();
  });

  it("ignores follow-up text when no follow-up date is chosen", async () => {
    const screen = setup();
    await typeNote(screen, "Note");
    fireEvent.press(screen.getByLabelText("1 week"));
    fireEvent.changeText(screen.getByPlaceholderText("About (optional)"), "something");
    fireEvent.press(screen.getByLabelText("None"));
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockAddOrgNote).toHaveBeenCalled());
    expect(mockAddOrgNote.mock.calls[0][1]).toMatchObject({ follow_up_date: null, follow_up_text: null });
  });

  it("can change only the stage, with no note", async () => {
    const screen = setup();
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Prospect"));
    fireEvent.press(screen.getByText("Save stage change"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddOrgNote).not.toHaveBeenCalled();
    expect(mockChangeDeal).toHaveBeenCalledWith(70, { stage: "prospect", status: "contacted" });
  });

  it("will not save when there is nothing to save", async () => {
    const screen = setup();
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    fireEvent.press(screen.getByText("Save note"));
    expect(mockAddOrgNote).not.toHaveBeenCalled();
    expect(mockChangeDeal).not.toHaveBeenCalled();
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("keeps the note on the screen and on the phone when saving fails", async () => {
    mockAddOrgNote.mockRejectedValue(new Error("no signal"));
    const screen = setup();
    await typeNote(screen, "Important: they want a proposal by Friday");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(screen.getByText(/Your note is kept on this phone/)).toBeTruthy());
    expect(screen.getByDisplayValue("Important: they want a proposal by Friday")).toBeTruthy();
    expect(mockBack).not.toHaveBeenCalled();
    expect(JSON.parse(Object.values(store)[0]).note).toBe("Important: they want a proposal by Friday");
    // and a second try works
    mockAddOrgNote.mockResolvedValue({ id: 2, follow_up_date: null });
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
  });

  it("if the note saved but the stage change failed, says so and retries only the stage", async () => {
    mockChangeDeal.mockRejectedValueOnce(new Error("boom"));
    const screen = setup();
    await typeNote(screen, "Met them");
    await waitFor(() => expect(screen.getByLabelText("Suspect")).toBeTruthy());
    fireEvent.press(screen.getByLabelText("Suspect"));
    fireEvent.press(screen.getByText("Save note and update stage"));
    await waitFor(() => expect(screen.getByText(/The note was saved, but the stage change failed/)).toBeTruthy());
    expect(mockBack).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue("Met them")).toBeNull(); // not shown twice, not posted twice
    fireEvent.press(screen.getByText("Retry stage change"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddOrgNote).toHaveBeenCalledTimes(1);
    expect(mockChangeDeal).toHaveBeenCalledTimes(2);
  });

  it("restores an unsent note, and shows it was restored", async () => {
    store["meeting_draft_v1:organization:42"] = JSON.stringify({
      note: "Typed in the car park", method: "phone", followUp: "2w", followUpText: "pricing",
    });
    const screen = setup();
    await waitFor(() => expect(screen.getByDisplayValue("Typed in the car park")).toBeTruthy());
    expect(screen.getByText("Your unsent note was restored.")).toBeTruthy();
    expect(screen.getByLabelText("Call").props.accessibilityState.selected).toBe(true);
    expect(screen.getByLabelText("2 weeks").props.accessibilityState.selected).toBe(true);
    expect(screen.getByDisplayValue("pricing")).toBeTruthy();
  });

  it("writes what is typed to the phone as it is typed", async () => {
    const screen = setup();
    await typeNote(screen, "half a thought");
    await waitFor(() => expect(JSON.parse(store["meeting_draft_v1:organization:42"]).note).toBe("half a thought"));
  });

  it("does not trample a stored draft with an empty form before it has loaded", async () => {
    store["meeting_draft_v1:organization:42"] = JSON.stringify({ note: "keep me", method: null, followUp: "none", followUpText: "" });
    const screen = setup();
    await waitFor(() => expect(screen.getByDisplayValue("keep me")).toBeTruthy());
    expect(JSON.parse(store["meeting_draft_v1:organization:42"]).note).toBe("keep me");
  });

  it("goes to the organization when there is nothing to go back to", async () => {
    mockCanGoBack.mockReturnValue(false);
    const screen = setup();
    await typeNote(screen, "x");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith({
      pathname: "/(drawer)/organization-detail", params: { id: "42" },
    }));
  });

  it("a note can be about another offer, or general, and then moves no deal", async () => {
    const screen = setup();
    await typeNote(screen, "Asked about the language app");
    fireEvent.press(await screen.findByLabelText("LearnWohl"));
    expect(screen.queryByLabelText("Suspect")).toBeNull(); // not pitched LearnWohl yet: no stage to move
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockAddOrgNote).toHaveBeenCalled());
    expect(mockAddOrgNote.mock.calls[0][1]).toMatchObject({ offer: "learnwohl" });
    expect(mockChangeDeal).not.toHaveBeenCalled();
  });

  it("is for the admin only", async () => {
    const screen = setup("organization", "viewer");
    await waitFor(() => expect(screen.getByText("Only the admin can log notes.")).toBeTruthy());
    expect(screen.queryByText("Save note")).toBeNull();
  });
});

describe("log a meeting — person", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    for (const k of Object.keys(store)) delete store[k];
    mockCanGoBack.mockReturnValue(true);
    mockAddPersonNote.mockResolvedValue({ id: 1 });
    mockChangeDeal.mockResolvedValue(deal(90, "person", "prospect", "contacted"));
  });

  it("saves a person note using the person vocabulary and tells the person screen to reload", async () => {
    const changed = jest.fn();
    const off = onChanged(personKey(7), changed);
    const screen = setup("person");
    await typeNote(screen, "Coffee with Anna");
    fireEvent.press(screen.getByLabelText("Drop-in"));
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddPersonNote).toHaveBeenCalledWith(7, "Coffee with Anna", "visit", null, "consulting");
    expect(mockAddOrgNote).not.toHaveBeenCalled();
    expect(changed).toHaveBeenCalledTimes(1);
    off();
  });

  it("sends typed minutes with a sit-down meeting or a video call", async () => {
    const screen = setup("person");
    await typeNote(screen, "Video call with Anna");
    fireEvent.press(screen.getByLabelText("Video call"));
    fireEvent.changeText(screen.getByLabelText("Minutes"), "40");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddPersonNote).toHaveBeenCalledWith(7, "Video call with Anna", "video", 40, "consulting");
  });

  it("offers the stage of the person's deal and a next step, saved with the note", async () => {
    const screen = setup("person");
    await waitFor(() => expect(screen.getByLabelText("Prospect")).toBeTruthy());
    expect(screen.getByText("Next step")).toBeTruthy();
    fireEvent.press(screen.getByLabelText("Prospect"));
    fireEvent.press(screen.getByText("Save stage change"));
    await waitFor(() => expect(mockChangeDeal).toHaveBeenCalledWith(90, { stage: "prospect", status: "contacted" }));
  });

  it("a person's follow-up becomes their next step, saved after the note", async () => {
    mockSetDealNextStep.mockResolvedValue({ next_step: "Invite to coffee", next_step_date: dateInDays(7), logged: true });
    const screen = setup("person");
    await typeNote(screen, "Met at the fair");
    fireEvent.press(screen.getByLabelText("1 week"));
    fireEvent.changeText(screen.getByPlaceholderText("About (optional)"), "Invite to coffee");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddPersonNote).toHaveBeenCalledWith(7, "Met at the fair", null, null, "consulting");
    // on the deal the note is about
    expect(mockSetDealNextStep).toHaveBeenCalledWith(90, "Invite to coffee", dateInDays(7));
  });

  it("can set only a next step, with no note", async () => {
    mockSetDealNextStep.mockResolvedValue({ next_step: "Follow up", next_step_date: dateInDays(1), logged: true });
    const screen = setup("person");
    await screen.findByLabelText("Prospect"); // the deal has loaded
    fireEvent.press(await screen.findByLabelText("Tomorrow"));
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddPersonNote).not.toHaveBeenCalled();
    expect(mockSetDealNextStep).toHaveBeenCalledWith(90, "Follow up", dateInDays(1));
  });

  it("if the note saved but the next step failed, says so and retries only the next step", async () => {
    mockSetDealNextStep.mockRejectedValueOnce(new Error("offline"));
    mockSetDealNextStep.mockResolvedValueOnce({ next_step: "Call", next_step_date: dateInDays(3), logged: true });
    const screen = setup("person");
    await screen.findByLabelText("Prospect"); // the deal has loaded
    await typeNote(screen, "Quick chat");
    fireEvent.press(screen.getByLabelText("3 days"));
    fireEvent.changeText(screen.getByPlaceholderText("About (optional)"), "Call");
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() =>
      expect(screen.getByText("Note saved, but the next step couldn't be saved. Try again.")).toBeTruthy(),
    );
    expect(mockBack).not.toHaveBeenCalled();
    fireEvent.press(screen.getByText("Save note"));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockAddPersonNote).toHaveBeenCalledTimes(1);
    expect(mockSetDealNextStep).toHaveBeenCalledTimes(2);
  });
});

describe("log a meeting — dictation", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    for (const k of Object.keys(store)) delete store[k];
    mockPermission.mockResolvedValue({ granted: true });
    mockTranscribeOrg.mockResolvedValue({ transcript: "Spoke to the owner" });
  });

  it("records, transcribes, and adds the text to the note for review", async () => {
    const screen = setup();
    await typeNote(screen, "Typed first");
    await act(async () => { fireEvent.press(screen.getByLabelText("Dictate")); });
    await waitFor(() => expect(mockRecorder.record).toHaveBeenCalled());
    await act(async () => { fireEvent.press(screen.getByLabelText("Stop")); });
    await waitFor(() => expect(mockTranscribeOrg).toHaveBeenCalledWith(42, "file:///rec.m4a"));
    await waitFor(() => expect(screen.getByDisplayValue("Typed first\nSpoke to the owner")).toBeTruthy());
    expect(mockAddOrgNote).not.toHaveBeenCalled(); // dictation stores nothing by itself
  });

  it("explains when the microphone is not allowed", async () => {
    mockPermission.mockResolvedValue({ granted: false });
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const screen = setup();
    await act(async () => { fireEvent.press(await screen.findByLabelText("Dictate")); });
    await waitFor(() => expect(alert).toHaveBeenCalled());
    expect(mockRecorder.record).not.toHaveBeenCalled();
    alert.mockRestore();
  });

  it("shows a message when the recording cannot be transcribed, and keeps what was typed", async () => {
    mockTranscribeOrg.mockRejectedValue({ response: { data: { detail: "Couldn't make out any speech — try again." } } });
    const screen = setup();
    await typeNote(screen, "Typed");
    await act(async () => { fireEvent.press(screen.getByLabelText("Dictate")); });
    await waitFor(() => expect(mockRecorder.record).toHaveBeenCalled());
    await act(async () => { fireEvent.press(screen.getByLabelText("Stop")); });
    await waitFor(() => expect(screen.getByText("Couldn't make out any speech — try again.")).toBeTruthy());
    expect(screen.getByDisplayValue("Typed")).toBeTruthy();
  });
});

describe("dateInDays", () => {
  it("uses the local calendar date, across month and year ends", () => {
    expect(dateInDays(1, new Date(2026, 0, 31, 23, 30))).toBe("2026-02-01");
    expect(dateInDays(7, new Date(2026, 11, 28, 9, 0))).toBe("2027-01-04");
    expect(dateInDays(0, new Date(2026, 9, 3))).toBe("2026-10-03");
  });
});

describe("typedMinutes", () => {
  it("is a whole number of minutes up to a day, or null", () => {
    expect(typedMinutes("45")).toBe(45);
    expect(typedMinutes(" 0 ")).toBe(0);
    for (const bad of ["", "abc", "-5", "1.5", "1441", "99999"]) expect(typedMinutes(bad)).toBeNull();
  });
});
