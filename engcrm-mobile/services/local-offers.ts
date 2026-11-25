import type { Offer } from "./deals";
import { type LocalBindValue, type LocalDatabase, withLocalRead, withLocalWrite } from "./local-transaction";

interface OffersDatabase extends LocalDatabase {
  getAllAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T[]>;
}

function parseOffers(value: unknown): Offer[] {
  if (!Array.isArray(value) || value.length > 2000) throw new Error("Invalid offline offers");
  const slugs = new Set<string>(), ids = new Set<number>();
  return value.map((offer: unknown) => {
    if (!offer || typeof offer !== "object" || !("id" in offer) || !("slug" in offer) || !("name" in offer) ||
        !("website" in offer) || !("revenue_kind" in offer) || !Number.isSafeInteger(offer.id) || (offer.id as number) < 1 ||
        typeof offer.slug !== "string" || !offer.slug.trim() || offer.slug.length > 100 ||
        typeof offer.name !== "string" || !offer.name.trim() || offer.name.length > 200 ||
        !(offer.website === null || (typeof offer.website === "string" && offer.website.length <= 300)) ||
        !["one_off", "subscription"].includes(String(offer.revenue_kind)) ||
        slugs.has(offer.slug) || ids.has(offer.id as number)) throw new Error("Invalid offline offer");
    slugs.add(offer.slug);
    ids.add(offer.id as number);
    return { id: offer.id as number, slug: offer.slug, name: offer.name, website: offer.website as string | null,
      revenue_kind: offer.revenue_kind as Offer["revenue_kind"] };
  });
}

export async function saveLocalOffers(database: OffersDatabase, payload: unknown): Promise<void> {
  const offers = parseOffers(payload);
  return withLocalWrite(database, async () => {
    await database.runAsync("UPDATE local_offers SET is_active=0");
    for (let index = 0; index < offers.length; index++) {
      const offer = offers[index];
      await database.runAsync("INSERT INTO local_offers(slug,server_id,name,website,revenue_kind,display_order,is_active) " +
        "VALUES (?,?,?,?,?,?,1) ON CONFLICT(slug) DO UPDATE SET server_id=excluded.server_id,name=excluded.name,website=excluded.website," +
        "revenue_kind=excluded.revenue_kind,display_order=excluded.display_order,is_active=1",
      offer.slug, offer.id, offer.name, offer.website, offer.revenue_kind, index);
    }
  });
}

export function readLocalOffers(database: OffersDatabase): Promise<Offer[]> {
  return withLocalRead(database, () => database.getAllAsync<Offer>(
    "SELECT server_id AS id,slug,name,website,revenue_kind FROM local_offers WHERE is_active=1 ORDER BY display_order,slug",
  ));
}
