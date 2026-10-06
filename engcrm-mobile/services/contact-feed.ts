import { client } from "./api";

export const CONTACT_FEED_PAGE_SIZE = 50;
export type ContactKind = "person" | "organization";
export type ContactSort = "last_contact" | "newest" | "name";

export interface ContactEntry {
  id: number;
  kind: ContactKind;
  name: string;
  description: string | null;
  company: string | null;
  city: string | null;
  email: string | null;
  phone: string | null;
  pipeline_stage: string | null;
  created_at: string | null;
  last_contact: string | null;
}

export function contactKey(contact: Pick<ContactEntry, "kind" | "id">): string {
  return `${contact.kind}-${contact.id}`;
}

export async function fetchContactFeed(filters: {
  search: string; kind: ContactKind | ""; stage: string; sort: ContactSort; page: number;
}): Promise<ContactEntry[]> {
  const response = await client.get("/api/contact-feed", { params: filters });
  return response.data;
}
