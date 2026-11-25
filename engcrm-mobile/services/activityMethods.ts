import type { MeetingMethod } from "./api";

export const ACTIVITY_METHODS: { value: MeetingMethod; labelKey: string }[] = [
  { value: "in_person", labelKey: "meeting.methodVisit" },
  { value: "meeting", labelKey: "meeting.methodMeeting" },
  { value: "phone", labelKey: "meeting.methodCall" },
  { value: "video", labelKey: "meeting.methodVideo" },
  { value: "email", labelKey: "meeting.methodEmail" },
  { value: "letter", labelKey: "meeting.methodPostMail" },
  { value: "linkedin", labelKey: "meeting.methodLinkedin" },
  { value: "linkedin_reply", labelKey: "meeting.methodLinkedinReply" },
  { value: "other", labelKey: "meeting.methodOther" },
];

export const PERSON_ACTIVITY_METHOD: Record<MeetingMethod, string> = {
  in_person: "visit", meeting: "meeting", phone: "call", video: "video", email: "email", letter: "letter",
  linkedin: "linkedin", linkedin_reply: "linkedin_reply", other: "other",
};
