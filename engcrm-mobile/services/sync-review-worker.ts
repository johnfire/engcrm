import { applyDeletionMarker } from "./local-pull";
import { type LocalBindValue, type LocalDatabase, withLocalRead, withLocalWrite } from "./local-transaction";
import type { SyncEntityKind } from "./sync-contracts";

interface ReviewDatabase extends LocalDatabase {
  getAllAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T[]>;
}

interface ReviewItem { mutation_id: string; entity_kind: SyncEntityKind; entity_sync_id: string }
interface ReviewOutcome { mutation_id: string; status: "pending" | "applied" | "recreated" | "discarded" | "expired" | "erased" }
const STATUSES = ["pending", "applied", "recreated", "discarded", "expired", "erased"];

function parseOutcomes(response: unknown, items: ReviewItem[]): ReviewOutcome[] {
  if (!response || typeof response !== "object" || !("outcomes" in response) || !Array.isArray(response.outcomes)) {
    throw new Error("Invalid review outcome response");
  }
  const expected = new Set(items.map((item) => item.mutation_id));
  return response.outcomes.map((outcome: unknown) => {
    if (!outcome || typeof outcome !== "object" || !("mutation_id" in outcome) || !("status" in outcome) ||
        typeof outcome.mutation_id !== "string" || !expected.delete(outcome.mutation_id) ||
        typeof outcome.status !== "string" || !STATUSES.includes(outcome.status)) throw new Error("Invalid review outcome");
    return outcome as ReviewOutcome;
  });
}

async function saveOutcomes(database: ReviewDatabase, items: ReviewItem[], outcomes: ReviewOutcome[]): Promise<void> {
  await withLocalWrite(database, async () => {
    for (const outcome of outcomes) {
      if (outcome.status === "pending") continue;
      const item = items.find((entry) => entry.mutation_id === outcome.mutation_id)!;
      if (outcome.status === "erased") {
        await applyDeletionMarker(database, { sequence: 0, entity_kind: item.entity_kind, sync_id: item.entity_sync_id,
          operation: "hard_erase", changed_at: new Date().toISOString() });
      } else {
        await database.runAsync("UPDATE local_provisional_changes SET status=? WHERE mutation_id=? AND status='review'",
          outcome.status, outcome.mutation_id);
      }
    }
  });
}

export async function synchronizeReviewOutcomes(database: ReviewDatabase, fetchOutcomes: (ids: string[]) => Promise<unknown>): Promise<void> {
  let after = "";
  while (true) {
    const items = await withLocalRead(database, () => database.getAllAsync<ReviewItem>(
      "SELECT mutation_id,entity_kind,entity_sync_id FROM local_provisional_changes " +
      "WHERE status='review' AND mutation_id>? ORDER BY mutation_id LIMIT 100", after,
    ));
    if (items.length === 0) return;
    const outcomes = parseOutcomes(await fetchOutcomes(items.map((item) => item.mutation_id)), items);
    await saveOutcomes(database, items, outcomes);
    after = items[items.length - 1].mutation_id;
  }
}
