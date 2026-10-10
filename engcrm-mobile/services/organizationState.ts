// The organization state vocabulary, mirroring gcrm/contact_state.py.
//
// Three independent axes: where the organization sits in the pipeline, what is
// going on with it right now, and which suppression facts are true of it.
//
// This file duplicates the Python definitions on purpose — the app has to know
// the vocabulary offline, before any request. tests/test_contact_state.py reads
// this file and fails if the two ever disagree, so the duplication cannot rot.

export const PIPELINE_STAGES = [
  "candidate",
  "suspect",
  "prospect",
  "opportunity",
  "customer",
  "not_in_pipeline",
] as const;

export const STATUSES = [
  "none",
  "ready",
  "contacted",
  "meeting",
  "proposal",
  "dormant",
  "on_hold",
  "dropped",
  "not_interested",
] as const;

export const SUPPRESSION_FLAGS = [
  "do_not_contact",
  "email_bounced",
  "research_exhausted",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];
export type OrganizationStatus = (typeof STATUSES)[number];
export type SuppressionFlag = (typeof SUPPRESSION_FLAGS)[number];

/** i18n key for a stage, status or flag value — one naming rule, no lookup tables. */
export function stageLabelKey(stage: string): string {
  return `stage.${stage}`;
}

export function statusLabelKey(status: string): string {
  return `status.${status}`;
}

export function flagLabelKey(flag: string): string {
  return `flag.${flag}`;
}

/** What normally goes with what — mirrors TYPICAL_STATUSES_BY_STAGE in
 *  gcrm/organization_state.py. Advisory: it orders the status choices and powers the
 *  "usual combination" hint; it never stops anyone from picking something else. */
export const TYPICAL_STATUSES_BY_STAGE: Record<PipelineStage, readonly OrganizationStatus[]> = {
  candidate: ["none", "ready"],
  suspect: ["ready", "contacted", "dormant", "on_hold"],
  prospect: ["contacted", "dormant", "on_hold"],
  opportunity: ["meeting", "proposal", "dormant", "on_hold"],
  customer: ["none", "dormant", "on_hold"],
  not_in_pipeline: ["not_interested", "dropped", "none"],
};

export function isTypicalPair(stage: PipelineStage, status: OrganizationStatus): boolean {
  return TYPICAL_STATUSES_BY_STAGE[stage].includes(status);
}
