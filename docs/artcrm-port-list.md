# artcrm → engcrm: difference & port list

Comparison of **artcrm** (`/home/chris/ppp2/artcrm`, the newer, more-evolved codebase) against **engcrm** (this repo, forked from an older artcrm). engcrm last synced from artcrm on **2026-04-19**; artcrm continued to **2026-06-20**. Goal: decide what to port forward.

Method: structural diff + four deep comparisons (agents, web-app core, tools+schema, new subsystems), normalizing the `artcrm_*`↔`gcrm_*` rename and the art→generic vertical wording (those are intentional, not "missing features").

**Big picture:** the two web apps are ~95% identical. The real divergence is in (a) **agent/tool data-quality improvements** engcrm regressed on or never received, (b) **standalone ops runners**, and (c) **whole new subsystems** (geographic targeting, cost tracking, marketing/strategy, and a mobile app + JSON API + push). A few areas engcrm is **ahead** — don't regress them.

---

## ⚠️ Where engcrm is AHEAD of artcrm — do NOT port back / don't regress
- **Per-user auth** — engcrm has email + bcrypt accounts (migration 014, `security.py`, unit-tested `authenticate()`, break-glass, DB-failure tolerance). artcrm still uses a single shared `ADMIN_PASSWORD`. Keep engcrm's.
- **Vertical architecture** — engcrm externalised everything domain-specific into `vertical.py` + `prompts/` package + `vertical_context.md` (+ `Mission.context`). artcrm hardcodes `ART_MISSION` in `config.py` and keeps prompts in the agent packages. engcrm's design is better; keep it.
- **`starred` contacts** (015), **`SESSION_COOKIE_SECURE`**, **scout case-insensitive `SCORED_TYPES_LC`** fix, **automatic enrichment** in the graph, **Open-Brain-learnings injected in outreach**. All engcrm-ahead.

---

## Tier 1 — Clear wins (low risk, high value). Port these.

### Enrichment quality (biggest single win — engcrm regressed to snippet-only)
- [ ] **Page fetching during enrichment** — artcrm fetches candidate pages and feeds real page text to the extractor (emails live on pages, not search snippets). engcrm uses snippets only. _needs `PageFetcher` dep wired into the enrichment factory._
- [ ] **Impressum/Kontakt German query** — DE/AT/CH → `"{name} {city} Impressum Kontakt"` (where German sites put emails) vs engcrm's generic query. Trivial, materially better recall.
- [ ] **Never-overwrite-existing-data guard** — artcrm only writes fields that were actually missing; engcrm's `apply_results` overwrites website/email/phone unconditionally → can clobber good data with worse LLM guesses. **Data-integrity bug fix.**

### Research agent
- [ ] **Website email-backfill** — for contacts with a website but no email, fetch the page, regex-extract an email, filter noise domains. Directly raises contactable-email yield.
- [ ] **Ignored-chains filter** — skip franchises/chains (fuzzy match ≥0.90) so they never enter the pipeline. _needs `ignored_chains` table + `ChainsFetcher` dep._

### Followup agent
- [ ] **Bounce detection → `bad_email`** — detect delivery-failure messages (DE+EN regexes), extract the failed recipient, mark the contact `bad_email` instead of LLM-classifying the bounce as "other". Stops re-emailing dead addresses. _needs `BounceHandler` dep + `bad_email` status seeded._

### db.py correctness/quality (tool layer)
- [ ] **`get_cold_contacts`** — exclude contacts already in `approval_queue`, order by `fit_score DESC`, add `city`/`scan_level`/`neighborhood`/`min_tier` filters. The approval-queue exclusion is a real correctness fix.
- [ ] **`match_contact_by_email`** — corporate-domain fallback (match `%@domain` when domain isn't freemail). No schema dependency.
- [ ] **`get_contacts_needing_enrichment`** — predicate "missing email" (not "missing website AND email"), exclude `cannot_find_more_data`/deleted, order `enriched_at NULLS FIRST`.
- [ ] **`google_maps_search`** — paginate up to 3 pages (≤60 results) via `nextPageToken` + extract `neighborhood` from address components. Strictly better discovery.
- [ ] **`update_contact_details`** — always stamp `enriched_at` (marks "processed") even when nothing changed.

### Standalone supervisor runners (engcrm can only run things inside the full graph)
- [ ] **`run_scout`** (`--limit/--city/--skip-galleries`), **`run_enrichment`** (`--city/--limit`), **`run_outreach`** (`--city/--limit/--level/--neighborhood/--min-tier`) — targeted re-runs. Mostly self-contained.
- [ ] **`run_blocked_report`** — SQL report of contacts blocked from outreach by city. _verify `consent_log` table exists in engcrm._
- [ ] **`run_email_audit`** — audit the IMAP Sent folder vs DB, upgrade mis-statused contacts to `contacted` (`--fix`).
- [ ] **`run_requeue_unsent`** — re-enrich cities with `approved_unsent` drafts, flip newly-emailable ones back to `pending`.
- [ ] **`run_interview`** — interactive post-visit debrief CLI. **engcrm is half-ready:** `vertical.py` already defines `INTERVIEW_APP_NAME`/`INTERVIEW_MATERIALS_OPTIONS` but nothing consumes them. Port and wire to those constants (don't hardcode "ArtCRM").
- [ ] **`run_followup`** — standalone followup (merges fresh IMAP + DB backlog). _needs the followup-agent factory signature reconciled first (the agent package diverged — see caveats)._

---

## Tier 2 — Worthwhile features (medium effort)

- [ ] **Neighborhood targeting** — `contacts.neighborhood` + `contacts.neighborhood_tier` (poor/normal/wealthy) + `neighborhood_tiers` lookup table + `min_tier` filtering in cold-contact selection (bias outreach toward wealthier areas). Schema is cheap; **populating tiers** needs the LLM rating scripts (`rate_neighborhoods.py`/`eval_neighborhoods.py`, Anthropic key) + a run. _Skip `city_size` (016) — it's seeded but **dead**, no code reads it._
- [ ] **Cost tracking** — `costs.py` (per-run LLM+search spend) + hooks in `llm.py`/`search.py`/`db.py` + a `run_costs` table (**no migration exists in artcrm — author one**). Self-contained; adopt as a bundle only if you want spend visibility.
- [ ] **Followup richer taxonomy** — 6-class (`interested/warm/not_interested/not_possible/opt_out/other`) vs engcrm's 4-class; `warm` triggers a "visit when nearby" flag + a low-pressure reply. _touches shared classify/draft prompts + adds `contacts.visit_when_nearby`. Keep engcrm's autonomous-send design — don't revert to artcrm's queue-only._
- [ ] **Pre-outreach reply guard** — only classify replies from contacts in post-outreach statuses (avoid misclassifying replies from not-yet-contacted contacts). Low effort.
- [ ] **Inbox classification audit trail** — persist *why* each inbox message was classified/skipped (`save_inbox_classification`). engcrm already has the columns (012) → clean drop-in.
- [ ] **Richer research page** — per-level "Sent L1–L5"/emailed columns + totals row. _needs `get_all_city_scan_status` to also return `emailed_by_level`/`total_contacts` (pure query change)._

---

## Tier 3 — Big / deliberate decisions

- [ ] **Marketing / strategy subsystem** — `src/marketing/` (research + strategy agents), `marketing_db` tool, `marketing_strategies/research/digests` tables, `marketing.py` router + `strategy.html` (two-pane markdown editor + weekly digest + observations feed). Produces a weekly marketing digest from strategy docs + pipeline stats. **Med effort**, but it's **art-marketing-flavored** (plein-air, markets) and pulls in LangChain/Anthropic/DeepSeek/Brave/Open-Brain + cron. Port only if engcrm grows an equivalent marketing function. _(Seed bug to fix on port: `marketing_strategies.doc_path` points at repo-root filenames but docs live under `docs/`.)_
- [ ] **Mobile experience** (dependency order):
  1. **Mobile JSON API** — 8 `api_*.py` routers + `jwt_auth.py` (HS256 JWT, `JWT_SECRET`, PyJWT) returning JSON under `/api/*`, CORS open. **Low–Med** (self-contained, but each query assumes artcrm's schema — reconcile column names to engcrm).
  2. **Push notifications** — Expo Push; `push_tokens` table + `api_push.py` register + `push.py` send + a hook in `queue_for_approval`. **Low** server-side, but useless without the app.
  3. **artcrm-mobile app** — Expo SDK 56 / React Native / TypeScript, expo-router, axios, SecureStore, EAS builds (Android, `de.christopherrehm.artcrm`). Phone front-end: approvals, inbox, contacts, activity, marketing, research. **High** — a whole separate codebase + native build/release pipeline (EAS/FCM), not just file copies. Base URL hardcoded to `crm.christopherrehm.de`.

---

## ⚠️ Caveats / landmines when porting
- **`save_contact` duplicate-return conflict** — engcrm returns `0` on a (name,city) duplicate (a contract we just fixed + documented; callers rely on falsy = "not newly created"). artcrm returns the **existing id**. Porting artcrm's `save_contact` (which also adds `scan_level`/`status`/`neighborhood` kwargs + email-dedup) **conflicts** — reconcile the return contract or it'll mis-count/re-process dupes.
- **`visit_when_nearby` is on different tables** — engcrm put it on `inbox_messages` (012); artcrm's `set_visit_when_nearby` writes `contacts.visit_when_nearby`. Add the **contacts** column or it throws at runtime.
- **Missing statuses** — `networking_visit` (artcrm 007) and `bad_email` are not seeded in engcrm's `lookup_values`. Add them with their features if statuses are FK-validated.
- **artcrm code without migrations** — `run_costs`, `contacts.visit_when_nearby`, and the inbox classification columns were applied out-of-band in artcrm (no CREATE in the repo). A clean engcrm port must **author the migration**, not just copy code.
- **Agent ports need supervisor wiring** — the Tier-1 agent improvements depend on injected deps engcrm's `create_*_agent` call sites don't provide yet (`ChainsFetcher`, `BounceHandler`, `VisitFlagSetter`, enrichment `PageFetcher`, a `status`-aware `save_contact`). Each port = agent file + factory arg + tool function, not just the agent file.

---

## Equivalent — nothing to port
Scout (engcrm ahead), Outreach (engcrm's `draft_email_prompt` is a superset), all agent `_utils.py` (byte-identical), all `state.py`, and the shared web routers `approval/drafts/inbox/people/activity/contacts/contact_detail` (semantically identical; template line-count gaps are just Prettier formatting).
