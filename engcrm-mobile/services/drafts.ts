// Unsent meeting notes, kept on the phone. A note typed in a car park must survive
// a dropped connection, a phone call, or the app being closed, so what is typed is
// written here as it is typed and removed only once the server has the note.
// Storage can fail (full disk, no permission): that never blocks writing the note.

import AsyncStorage from "@react-native-async-storage/async-storage";

const PREFIX = "meeting_draft_v1:";

export interface MeetingDraft {
  note: string;
  method: string | null;
  followUp: string; // an option id such as "1w"; "none" for no follow-up
  followUpText: string;
}

export async function loadDraft(key: string): Promise<MeetingDraft | null> {
  try {
    const raw = await AsyncStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.note !== "string") return null;
    return {
      note: parsed.note,
      method: typeof parsed.method === "string" ? parsed.method : null,
      followUp: typeof parsed.followUp === "string" ? parsed.followUp : "none",
      followUpText: typeof parsed.followUpText === "string" ? parsed.followUpText : "",
    };
  } catch {
    return null;
  }
}

/** Store the draft; an empty one is removed instead of kept. */
export async function saveDraft(key: string, draft: MeetingDraft): Promise<void> {
  try {
    if (!draft.note.trim() && !draft.followUpText.trim()) {
      await AsyncStorage.removeItem(PREFIX + key);
      return;
    }
    await AsyncStorage.setItem(PREFIX + key, JSON.stringify(draft));
  } catch {
    // keep going: the screen still holds the text
  }
}

export async function clearDraft(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(PREFIX + key);
  } catch {
    // nothing to do
  }
}
