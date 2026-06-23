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

// --- Card capture ---
// Upload a card photo (multipart). Don't set Content-Type — RN sets the
// multipart boundary itself; overriding it drops the boundary and breaks parsing.
export async function captureCard(
  imageUri: string,
  gps?: { lat: number; lng: number },
): Promise<CaptureResult> {
  const form = new FormData();
  form.append("image", { uri: imageUri, name: "card.jpg", type: "image/jpeg" } as any);
  if (gps) {
    form.append("gps_lat", String(gps.lat));
    form.append("gps_lng", String(gps.lng));
  }
  const resp = await client.post("/api/cards", form, { timeout: 60000 });
  return resp.data;
}

export async function confirmCard(
  captureId: number,
  fields: CardFields,
  linkToContactId?: number | null,
): Promise<{ contact_id: number; capture_id: number }> {
  const resp = await client.post(`/api/cards/${captureId}/confirm`, {
    fields,
    link_to_contact_id: linkToContactId ?? null,
  });
  return resp.data;
}

export async function discardCard(captureId: number): Promise<void> {
  await client.post(`/api/cards/${captureId}/discard`);
}

export async function listPendingCards(): Promise<PendingCard[]> {
  const resp = await client.get("/api/cards", {
    params: { status: "pending_review" },
  });
  return resp.data;
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

export interface CardFields {
  is_card?: boolean;
  confidence?: number | null;
  company?: string | null;
  name?: string | null;
  title?: string | null;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  website?: string | null;
  address?: string | null;
  city?: string | null;
  country?: string | null;
  industry?: string | null;
  language?: string | null;
  note?: string | null;
  error?: string;
}

export interface DupSuggestion {
  id: number;
  name: string;
  city: string | null;
  email: string | null;
  phone: string | null;
}

export interface CaptureResult {
  capture_id: number;
  is_card: boolean;
  confidence: number | null;
  fields: CardFields;
  dup_suggestion: DupSuggestion | null;
  cost_usd: number;
}

export interface PendingCard {
  id: number;
  captured_at: string;
  status: string;
  extraction_status: string;
  confidence: number | null;
  extracted: CardFields | null;
  dup_contact_id: number | null;
  contact_id: number | null;
}

// --- Voice capture ---
export async function processVoice(audioUri: string): Promise<VoiceResult> {
  const form = new FormData();
  form.append("audio", { uri: audioUri, name: "memo.m4a", type: "audio/m4a" } as any);
  const resp = await client.post("/api/voice", form, { timeout: 120000 });
  return resp.data;
}

export async function confirmVoice(body: {
  contact_id?: number | null;
  new_contact_name?: string | null;
  summary: string;
  follow_up_date?: string | null;
  follow_up_text?: string | null;
}): Promise<{ contact_id: number }> {
  const resp = await client.post("/api/voice/confirm", body);
  return resp.data;
}

export interface VoiceCandidate {
  id: number;
  name: string;
  city: string | null;
  email: string | null;
  phone: string | null;
  decision_maker: string | null;
}

export interface VoiceResult {
  transcript: string;
  summary: string;
  contact_query: string | null;
  follow_up_date: string | null;
  follow_up_text: string | null;
  is_new_lead: boolean;
  candidates: VoiceCandidate[];
}
