import { client } from "./api";
import { ContactKind } from "./contact-feed";

export interface ContactDateRecord {
  id: number;
  kind: ContactKind;
  name: string;
  interaction_id: number | null;
  contact_date: string | null;
}

export async function fetchContactDate(kind: ContactKind, id: number): Promise<ContactDateRecord> {
  const response = await client.get(`/api/contact-feed/${kind}/${id}/date`);
  return response.data;
}

export async function saveContactDate(record: ContactDateRecord, selected: string): Promise<ContactDateRecord> {
  const response = await client.patch(`/api/contact-feed/${record.kind}/${record.id}/date`, {
    contact_date: selected, interaction_id: record.interaction_id, previous_date: record.contact_date,
  });
  return response.data;
}
