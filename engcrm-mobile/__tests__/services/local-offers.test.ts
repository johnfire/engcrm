import { DatabaseSync } from "node:sqlite";

import { readLocalOffers, saveLocalOffers } from "../../services/local-offers";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  const database = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    getAllAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => sqlite.prepare(sql).all(...values) as T[],
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const result = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(result.lastInsertRowid), changes: Number(result.changes) };
    },
  };
  return { sqlite, database };
}

it("caches every active offer, including offers without deals, and retains archived rows", async () => {
  const { sqlite, database } = setup();
  try {
    const offers = [{ id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" },
      { id: 2, slug: "training", name: "Training", website: null, revenue_kind: "one_off" }];
    await saveLocalOffers(database, offers);
    expect(await readLocalOffers(database)).toEqual(offers);
    await saveLocalOffers(database, [offers[1]]);
    expect(await readLocalOffers(database)).toEqual([offers[1]]);
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_offers").get()).toEqual({ n: 2 });
  } finally { sqlite.close(); }
});

it("keeps the previous offer cache when the response is invalid", async () => {
  const { sqlite, database } = setup();
  try {
    const offer = { id: 1, slug: "consulting", name: "Consulting", website: null, revenue_kind: "one_off" };
    await saveLocalOffers(database, [offer]);
    await expect(saveLocalOffers(database, [{ ...offer, slug: "" }])).rejects.toThrow();
    expect(await readLocalOffers(database)).toEqual([offer]);
  } finally { sqlite.close(); }
});
