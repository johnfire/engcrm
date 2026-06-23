import axios from "axios";
import { getToken } from "./auth";

export const API_BASE = "https://engcrm.christopherrehm.de";

export function buildHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

const client = axios.create({ baseURL: API_BASE });

client.interceptors.request.use(async (config) => {
  const token = await getToken();
  if (token) config.headers["Authorization"] = `Bearer ${token}`;
  return config;
});

// --- Auth ---
// engcrm uses per-user accounts: login with email + password.
export async function login(
  email: string,
  password: string,
): Promise<{ token: string; role: string }> {
  const resp = await client.post("/api/auth/token", { email, password });
  return resp.data;
}

// --- Push ---
export async function registerPushToken(pushToken: string): Promise<void> {
  await client.post("/api/push/register", { token: pushToken });
}

// --- Approvals ---
export async function fetchApprovals(): Promise<Approval[]> {
  const resp = await client.get("/api/approvals");
  return resp.data;
}
export async function approveEmail(id: number): Promise<void> {
  await client.post(`/api/approvals/${id}/approve`);
}
export async function rejectEmail(id: number, reason: string): Promise<void> {
  await client.post(`/api/approvals/${id}/reject`, { reason });
}

// --- Inbox ---
export async function fetchInbox(): Promise<InboxMessage[]> {
  const resp = await client.get("/api/inbox");
  return resp.data;
}
export async function classifyMessage(
  id: number,
  classification: string,
): Promise<void> {
  await client.post(`/api/inbox/${id}/classify`, { classification });
}

// --- Contacts ---
export async function fetchContacts(params: {
  search?: string;
  status?: string;
  page?: number;
}): Promise<Contact[]> {
  const resp = await client.get("/api/contacts", { params });
  return resp.data;
}
export async function fetchContact(id: number): Promise<ContactDetail> {
  const resp = await client.get(`/api/contacts/${id}`);
  return resp.data;
}

// --- Activity ---
export async function fetchActivity(): Promise<AgentRun[]> {
  const resp = await client.get("/api/activity");
  return resp.data;
}

// --- Research ---
export async function runResearch(
  city: string,
  level: number,
  country = "DE",
): Promise<void> {
  await client.post("/api/research/run", { city, level, country });
}

// --- Types ---
export interface Approval {
  id: number;
  draft_subject: string;
  draft_body: string;
  created_at: string;
  contact_id: number;
  name: string;
  city: string;
  email: string;
  website: string | null;
}

export interface InboxMessage {
  id: number;
  from_email: string;
  subject: string;
  body: string;
  received_at: string;
  classification: string | null;
  contact_id: number | null;
  contact_name: string | null;
  city: string | null;
}

export interface Contact {
  id: number;
  name: string;
  city: string;
  country: string;
  type: string;
  status: string;
  email: string | null;
  website: string | null;
  fit_score: number | null;
  flagged: boolean;
  starred: boolean;
  last_contact: string | null;
}

export interface ContactDetail extends Contact {
  phone: string | null;
  notes: string | null;
  interactions: Interaction[];
}

export interface Interaction {
  interaction_date: string;
  method: string | null;
  direction: string | null;
  summary: string | null;
  outcome: string | null;
}

export interface AgentRun {
  id: number;
  agent_name: string;
  status: "running" | "completed" | "failed";
  summary: string | null;
  started_at: string;
  finished_at: string | null;
}
