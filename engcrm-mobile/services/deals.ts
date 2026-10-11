// Offers and deals: what is for sale, and one deal per offer pitched to an
// organization or person — its own stage, status, contact person, next step and
// money. See docs/plans/2026-10-10-offers-and-deals-design.md (phase 4).
//
// The lists remember which offer's pipeline they show, and the creation forms
// the offer used last, on the phone itself (AsyncStorage), like the web does per
// browser session.
import AsyncStorage from "@react-native-async-storage/async-storage";

import { client } from "./api";
import { OrganizationStatus, PipelineStage } from "./organizationState";

export interface Offer {
  id: number;
  slug: string;
  name: string;
  website: string | null;
  revenue_kind: "one_off" | "subscription";
}

export interface Subscription {
  id: number;
  amount_eur_month: string;
  started_on: string;
  ended_on: string | null;
  note: string | null;
}

export interface DealMoney {
  sales_total: string;
  sales: { id: number; amount_eur: string; won_on: string; description: string | null }[];
  subscriptions: Subscription[];
  running: Subscription | null;
}

export interface Deal {
  id: number;
  offer_id: number;
  offer_slug: string;
  offer_name: string;
  revenue_kind: "one_off" | "subscription";
  offer_archived: boolean;
  contact_id: number | null;
  person_id: number | null;
  pipeline_stage: PipelineStage;
  status: OrganizationStatus;
  next_step: string | null;
  next_step_date: string | null;
  contact_person_id: number | null;
  contact_person_name: string | null;
  organization_name?: string;
  money?: DealMoney;
}

/** A deal as the lists carry it: just enough for a chip. */
export interface DealChip {
  id: number;
  offer: string;
  slug: string;
  stage: PipelineStage;
  status: OrganizationStatus;
}

export type Owner = "organization" | "person";

export async function fetchOffers(): Promise<Offer[]> {
  return (await client.get("/api/offers")).data;
}

export async function fetchOrganizationDeals(id: number): Promise<Deal[]> {
  return (await client.get(`/api/contacts/${id}/deals`)).data;
}

export async function fetchPersonDeals(id: number): Promise<{ owned: Deal[]; contact_person_for: Deal[] }> {
  return (await client.get(`/api/people/${id}/deals`)).data;
}

export async function fetchDeals(owner: Owner, id: number): Promise<Deal[]> {
  return owner === "organization" ? fetchOrganizationDeals(id) : (await fetchPersonDeals(id)).owned;
}

export async function createDeal(owner: Owner, ownerId: number, offerId: number): Promise<{ id: number }> {
  return (await client.post("/api/deals", { owner, owner_id: ownerId, offer_id: offerId })).data;
}

export interface DealChange {
  stage?: PipelineStage;
  status?: OrganizationStatus;
  /** null clears it; leave it out to keep it */
  contact_person_id?: number | null;
}

export async function changeDeal(id: number, change: DealChange): Promise<Deal> {
  return (await client.patch(`/api/deals/${id}`, change)).data;
}

export async function setDealNextStep(
  id: number,
  nextStep: string | null,
  date: string | null,
): Promise<{ next_step: string | null; next_step_date: string | null }> {
  return (await client.put(`/api/deals/${id}/next-step`, { next_step: nextStep, next_step_date: date })).data;
}

export async function removeDeal(id: number): Promise<void> {
  await client.delete(`/api/deals/${id}`);
}

/** Start the deal's subscription, or change its price from `startedOn`. */
export async function startSubscription(id: number, amountEurMonth: string, startedOn: string): Promise<void> {
  await client.post(`/api/deals/${id}/subscription`, { amount_eur_month: amountEurMonth, started_on: startedOn });
}

/** End the running subscription; `endedOn` is the last day paid for. */
export async function endSubscription(id: number, endedOn: string): Promise<void> {
  await client.post(`/api/deals/${id}/subscription/end`, { ended_on: endedOn });
}

/** What a new note is about when nobody picks: the offer of the one open deal
 *  (any stage but not_in_pipeline), else general. The server applies the same rule
 *  when the phone sends no offer. */
export function defaultLogOffer(deals: Pick<Deal, "offer_slug" | "pipeline_stage">[]): string {
  const open = [...new Set(deals.filter((d) => d.pipeline_stage !== "not_in_pipeline").map((d) => d.offer_slug))];
  return open.length === 1 ? open[0] : GENERAL;
}

export const GENERAL = "general";
export const ALL_OFFERS = "all";

const FILTER_KEY = "offerFilter";
const LAST_OFFER_KEY = "lastOffer";

/** Which offer's pipeline the lists show: a slug, or "all". Unreadable storage is "all". */
export async function getOfferFilter(): Promise<string> {
  try {
    return (await AsyncStorage.getItem(FILTER_KEY)) || ALL_OFFERS;
  } catch {
    return ALL_OFFERS;
  }
}

export async function setOfferFilter(offer: string): Promise<void> {
  try {
    await AsyncStorage.setItem(FILTER_KEY, offer);
  } catch {
    // remembering is a convenience; the list still shows what was picked
  }
}

/** The offer a new organization or person goes into: the one used last, else consulting. */
export async function getLastOffer(): Promise<string> {
  try {
    return (await AsyncStorage.getItem(LAST_OFFER_KEY)) || "consulting";
  } catch {
    return "consulting";
  }
}

export async function setLastOffer(offer: string): Promise<void> {
  try {
    await AsyncStorage.setItem(LAST_OFFER_KEY, offer);
  } catch {
    // as above
  }
}
