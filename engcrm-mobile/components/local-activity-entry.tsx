import { formatDay } from "../services/dates";
import type { LocalRecord } from "../services/local-records";
import { ActivityEntry } from "./ActivityEntry";

function textField(fields: Record<string, unknown>, name: string): string | null {
  return typeof fields[name] === "string" ? fields[name] as string : null;
}

function textList(fields: Record<string, unknown>, name: string): string[] {
  const values = fields[name];
  return Array.isArray(values) ? values.filter((value): value is string => typeof value === "string") : [];
}

export function LocalActivityEntry({ record, owner }: { record: LocalRecord; owner: "person" | "organization" }) {
  const fields = record.fields;
  const date = textField(fields, owner === "person" ? "occurred_at" : "interaction_date");
  return <ActivityEntry owner={owner} entry={{
    when: formatDay(date) || date || "—",
    method: textField(fields, "method"),
    text: textField(fields, owner === "person" ? "note" : "summary"),
    durationMinutes: typeof fields.duration_minutes === "number" ? fields.duration_minutes : null,
    offer: textField(fields, "offer_slug"), direction: textField(fields, "direction"),
    attitude: textList(fields, "attitude"), myRead: textList(fields, "my_read"),
    materialsLeft: textField(fields, "materials_left"), outcome: textField(fields, "outcome"),
    nextAction: textField(fields, "next_action"), nextActionDate: textField(fields, "next_action_date"),
  }} />;
}
