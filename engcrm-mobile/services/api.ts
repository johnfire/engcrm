import axios from "axios";
import { router } from "expo-router";
import { clearToken, getToken } from "./auth";

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

// A 401 from any endpoint except the login call itself means our stored token is
// gone — expired (now a 30-day window) or revoked server-side. Rather than let
// every screen blank out on its own failed fetch, drop the dead token and bounce
// to login so the user just re-authenticates. The login screen handles its own
// 401 (wrong password). redirectingToLogin de-dupes the burst of 401s when
// several screens fetch at once; a later success clears it for the next session.
let redirectingToLogin = false;
client.interceptors.response.use(
  (response) => {
    redirectingToLogin = false;
    return response;
  },
  async (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    if (status === 401 && !url.includes("/api/auth/token") && !redirectingToLogin) {
      redirectingToLogin = true;
      await clearToken();
      router.replace("/login");
    }
    return Promise.reject(error);
  },
);

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

// Who-am-I — called at app cold start and on every foreground transition so
// the account's ui_language (and role) stay close to the DB without a push
// having to arrive first. See engcrm-mobile/i18n/.
export async function fetchMe(): Promise<{ email: string; role: string; ui_language: string }> {
  const resp = await client.get("/api/auth/me");
  return resp.data;
}

// Updates the account's interface-language preference. Triggers a silent push
// (server-side) so any other signed-in device for this account refreshes too.
export async function updateLanguage(uiLanguage: string): Promise<{ ui_language: string }> {
  const resp = await client.patch("/api/account/language", { ui_language: uiLanguage });
  return resp.data;
}

// --- Help Centre ---
export interface HelpArticle {
  id: number;
  slug: string;
  category: string;
  surfaces: string[];
  title: string;
  summary: string;
  body: string;
}

export async function fetchHelp(query = ""): Promise<HelpArticle[]> {
  const resp = await client.get("/api/help", { params: { q: query } });
  return resp.data;
}

export async function sendHelpFeedback(articleId: number, helpful: boolean, comment = ""): Promise<void> {
  await client.post("/api/help/feedback", { article_id: articleId, helpful, comment });
}

export async function completeHelpTour(): Promise<void> {
  await client.post("/api/help/tour/complete");
}

export async function fetchHelpTourStatus(): Promise<{ completed: boolean }> {
  const resp = await client.get("/api/help/tour");
  return resp.data;
}

// Always resolves — the backend never reveals whether the email matched an
// account. Actual password reset happens via the emailed link, opened in the
// phone's browser (same /reset-password page the web app uses).
export async function requestPasswordReset(email: string): Promise<void> {
  await client.post("/api/auth/reset-request", { email });
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
export type ContactSortKey = "created_at" | "name" | "type";

export async function fetchContacts(params: {
  search?: string;
  status?: string;
  page?: number;
  sort?: ContactSortKey;
  dir?: "asc" | "desc";
}): Promise<Contact[]> {
  const resp = await client.get("/api/contacts", { params });
  return resp.data;
}
export async function fetchContact(id: number): Promise<ContactDetail> {
  const resp = await client.get(`/api/contacts/${id}`);
  return resp.data;
}

// Run a fresh opportunity assessment for one contact (admin only, 403
// otherwise). Synchronous server-side — it fetches the company website and
// runs the LLM — so allow a generous timeout. Returns the stored analysis.
export async function runOpportunityAnalysis(
  id: number,
): Promise<OpportunityAnalysis | null> {
  const resp = await client.post(
    `/api/contacts/${id}/opportunity-analysis`,
    {},
    { timeout: 120000 },
  );
  return resp.data.opportunity_analysis ?? null;
}

// --- Activity ---
export async function fetchActivity(): Promise<AgentRun[]> {
  const resp = await client.get("/api/activity");
  return resp.data;
}

// --- Pipeline ---
// Run a single stage (research/scout/enrichment/outreach/followup) or the whole
// city pipeline ("all"). Followup is global and ignores city/level.
export async function runPipelineStage(
  stage: string,
  opts: { city?: string; level?: number; country?: string } = {},
): Promise<void> {
  await client.post(`/api/pipeline/${stage}/run`, {
    city: opts.city ?? "",
    level: opts.level ?? null,
    country: opts.country ?? "DE",
  });
}

// --- Research overview (read-only city scan-status table — display parity with
// the web Research page). Shaped server-side by build_research_overview(). ---
export async function fetchResearchOverview(): Promise<ResearchOverview> {
  const resp = await client.get("/api/research/overview");
  return resp.data;
}

export interface ResearchScan {
  level: number;
  last_run_at: string | null;
  contacts_found: number | null;
  run_count: number | null;
  due_for_rerun: boolean | null;
  complete: boolean | null;
}

export interface ResearchLevel {
  level: number;
  scan: ResearchScan | null;
  emailed: number;
}

export interface ResearchCity {
  id: number;
  city: string | null;
  country: string | null;
  region: string | null;
  levels: ResearchLevel[];
  emailed_total: number;
  total_contacts: number;
  scanned_levels: number;
}

export interface ResearchOverview {
  cities: ResearchCity[];
  levels: number[];
  // JSON object keys are strings, so level_labels arrives keyed by "1".."10".
  level_labels: Record<string, string>;
  total: number;
  level1_done: number;
  unscanned: number;
  totals: { contacts: number; emailed: number };
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

// --- Sign capture (storefront sign -> business name -> Places match -> research) ---
// Same multipart shape as captureCard — don't set Content-Type, RN sets the boundary.
export async function captureSign(
  imageUri: string,
  gps?: { lat: number; lng: number },
): Promise<SignCaptureResult> {
  const form = new FormData();
  form.append("image", { uri: imageUri, name: "sign.jpg", type: "image/jpeg" } as any);
  if (gps) {
    form.append("gps_lat", String(gps.lat));
    form.append("gps_lng", String(gps.lng));
  }
  const resp = await client.post("/api/signs", form, { timeout: 60000 });
  return resp.data;
}

export async function confirmSign(
  captureId: number,
  businessName: string,
  acceptPlace: boolean,
  linkToContactId?: number | null,
): Promise<{ contact_id: number; capture_id: number }> {
  const resp = await client.post(`/api/signs/${captureId}/confirm`, {
    business_name: businessName,
    accept_place: acceptPlace,
    link_to_contact_id: linkToContactId ?? null,
  });
  return resp.data;
}

export async function discardSign(captureId: number): Promise<void> {
  await client.post(`/api/signs/${captureId}/discard`);
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
  created_at: string;
}

export interface ContactDetail extends Contact {
  phone: string | null;
  notes: string | null;
  interactions: Interaction[];
  opportunity_analysis: OpportunityAnalysis | null;
}

export interface RecommendedService {
  service: string;
  outcome: string;
  rationale: string;
}

// The explainable AI/software opportunity assessment produced by the
// opportunity agent. Scores are 0–100. Mirrors the web contact-detail render.
export interface OpportunityAnalysis {
  opportunity_score: number | null;
  confidence_score: number | null;
  priority_score: number | null;
  fit_reasoning: string | null;
  suggested_approach: string | null;
  evidence: string[];
  recommended_services: RecommendedService[];
  discovery_questions: string[];
  analysis_date: string | null;
  model_used: string | null;
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

export interface SignFields {
  is_sign?: boolean;
  confidence?: number | null;
  business_name?: string | null;
  business_type?: string | null;
  phone?: string | null;
  website?: string | null;
  tagline?: string | null;
  language?: string | null;
  note?: string | null;
  error?: string;
}

// A Google Place resolved from the sign's business name + GPS. The confirm
// screen shows this and lets the user accept or reject it before a contact
// is created — a wrong match otherwise pollutes the CRM (see api_signs.py).
export interface SignPlace {
  name: string;
  place_id: string;
  address: string;
  city: string;
  website: string;
  phone: string;
}

export interface SignCaptureResult {
  capture_id: number;
  is_sign: boolean;
  confidence: number | null;
  fields: SignFields;
  place: SignPlace | null;
  dup_suggestion: DupSuggestion | null;
  cost_usd: number;
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

// --- People (individuals on scanned cards, linked to their company contact) ---
export type PersonSortKey = "created_at" | "name";

export async function fetchPeople(params: {
  search?: string;
  sort?: PersonSortKey;
  dir?: "asc" | "desc";
} = {}): Promise<Person[]> {
  const resp = await client.get("/api/people", { params });
  return resp.data;
}
export async function fetchPerson(id: number): Promise<Person> {
  const resp = await client.get(`/api/people/${id}`);
  return resp.data;
}

export interface Person {
  id: number;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  city: string | null;
  country: string | null;
  relationship: string | null;
  notes: string | null;
  contact_id: number | null;
  company: string | null;
  source: string | null;
  created_at: string;
}

// --- Recon (nearby contacts for on-foot field visits) ---
export async function fetchRecon(
  lat: number,
  lng: number,
  notContacted = false,
  limit = 50,
): Promise<ReconContact[]> {
  const resp = await client.get("/api/recon", {
    params: { lat, lng, not_contacted: notContacted, limit },
  });
  return resp.data;
}

export interface ReconContact {
  id: number;
  name: string;
  type: string | null;
  city: string | null;
  latitude: number;
  longitude: number;
  rating: number | null;
  user_ratings: number | null;
  business_status: string | null;
  status: string | null;
  fit_score: number | null;
  phone: string | null;
  website: string | null;
  maps_uri: string | null;
  distance_m: number;
}
