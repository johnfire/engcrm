import { client } from "./api";
import type { DealChip } from "./deals";

export const CONTACT_FEED_PAGE_SIZE = 50;
export type ContactKind = "person" | "organization";
export type ContactSort = "last_contact" | "newest" | "name";

export interface ContactPerson {
  id: number;
  name: string;
  description: string | null;
  email: string | null;
  phone: string | null;
  city: string | null;
  pipeline_stage: string | null;
  last_contact: string;
}

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
  deals?: DealChip[];
  created_at: string | null;
  last_contact: string | null;
  people?: ContactPerson[];
  last_contact_kind?: ContactKind;
  last_contact_id?: number;
  last_contact_name?: string;
}

export function contactKey(contact: Pick<ContactEntry, "kind" | "id">): string {
  return `${contact.kind}-${contact.id}`;
}

export async function fetchContactFeed(filters: {
  search: string; kind: ContactKind | ""; stage: string; sort: ContactSort; page: number;
  offer?: string; // a slug: that pipeline only; "all": every offer, each deal in `deals`
}): Promise<ContactEntry[]> {
  const response = await client.get("/api/contact-feed", { params: filters });
  return response.data;
}

export interface ContactCounts {
  month: { people: number; organizations: number };
  since_start: { people: number; organizations: number };
  business_start: string;
}

export async function fetchContactCounts(offer?: string): Promise<ContactCounts> {
  const response = await client.get("/api/contact-feed/counts", { params: offer && offer !== "all" ? { offer } : {} });
  return response.data;
}
