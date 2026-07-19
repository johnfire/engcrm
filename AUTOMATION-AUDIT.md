# Cross-App Automation Audit — "From Data Entry to Data Use"

*Generated 2026-06-23. A leverage-ranked backlog of workflow-automation opportunities across the live apps, found by auditing each repo for the **human-as-data-pipe** pattern.*

The target: anywhere a person manually enters, copies, organizes, or retypes data between where it **enters** (a photo, a file, an email, a card, a document, a URL, a voice) and where it's **used** (published, sent, displayed, studied, decided). Every one is the same move:

> **capture → AI extracts & structures → you approve → it flows into the pipeline.**

Two are already shipped in engcrm: business-card photo → lead, voice memo → interaction + follow-up.

---

## Status — updated 2026-06-24

Progress since this audit was written:
- ✅ **#1 — re-enable inbound-reply drafter (queue-only): DONE.** engcrm converted to queue-only + enabled + **deployed to prod**; gencrm fixed + committed locally; artcrm was already queue-only + on. The autonomous-send path was *removed entirely* — no code can email a lead without your approval.
- ✅ **Forward-email → task: DONE + deployed.** Forward any mail to `contact+task@christopherrehm.de` → a notes-world **Task** within ~20 min (VPS systemd sweep; mail-mcp `to` filter + plus-addressing; Message-ID dedup).
- ✅ **Auto-tag at capture: already shipped** — turned out *not* to need an LLM. Capturing inside a tag view already inherits that tag (notes-world, live since 2026-06-09). The audit oversold this one.
- 📋 **job-hunter ideas → GitHub issues** (removed from the list): recruiter-email→status `johnfire/job-hunter#13`, LinkedIn-screenshot→pipeline `#14`, project/metric→article-digest `#15`.
- ⏭ **Photo/whiteboard → note: deferred** (skipped for now).

The matrix below carries a **Status** column reflecting this.

---

## The headline insight: engcrm is now the parts bin

Most of this backlog is **porting + wiring, not building**. engcrm already proved and deployed the reusable pieces:
- **Claude vision** (card extraction) — reusable for any photo→data.
- **Self-hosted Whisper** (voice entry) — reusable for any voice→data.
- **The approval queue** — reusable for any AI-draft→human-approve.
- **The capture/confirm mobile screens** — copy-adapt templates.

And a recurring finding across apps: **the AI logic often already exists** (an MCP tool, a classifier, a reply-drafter) but there's **no in-app trigger**, or it's **disabled**. A lot of value here is just connecting existing capability to a capture surface. That's why most of the effort estimates are **S**, not L.

---

## Scored matrix (the judgment, made explicit)

Each opportunity scored 1–5 per axis (higher = more reason to automate). **Effort** is the separate cost (XS/S/M). Sorted by total /25. Scores are my reasoned judgment — re-weight as you see fit (avoidance + drift are the "hidden value" axes a stopwatch misses).

| Opportunity | App | Freq | Avoid | Drift | Mech | Reuse | **/25** | Effort | Status |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Painting → auto-catalogue (vision) | art-platform | 4 | 5 | 4 | 4 | 5 | **22** | S | **← next up** |
| Re-enable inbound-reply drafter | artcrm (→3) | 3 | 4 | 4 | 4 | 5 | **20** | XS | ✅ done 2026-06-24 |
| Auto-tag/type/due at capture | notes-world | 5 | 4 | 3 | 4 | 4 | **20** | S | ✅ already built |
| Recruiter email → status | job-hunter | 3 | 3 | 5 | 4 | 4 | **19** | S | 📋 issue #13 |
| LinkedIn screenshot → pipeline | job-hunter | 4 | 4 | 2 | 5 | 4 | **19** | S | 📋 issue #14 |
| Email-signature → contact enrich | artcrm (→3) | 3 | 4 | 3 | 5 | 4 | **19** | S | open |
| Voice capture (note/deck/blog) | notes/fk/art | 4 | 5 | 2 | 3 | 5 | **19** | S–M | open |
| Photo/whiteboard → note (vision) | notes-world | 3 | 4 | 2 | 4 | 5 | **18** | M | ⏭ deferred |
| Forward-email → task | notes-world | 3 | 4 | 3 | 4 | 4 | **18** | M | ✅ done 2026-06-24 |
| `maybe`-pile AI re-review | artcrm (→3) | 2 | 4 | 3 | 4 | 5 | **18** | S | open |
| Post-visit digest → follow-ups | artcrm (→3) | 2 | 3 | 4 | 4 | 4 | **17** | S–M | open |
| Inquiry → AI-drafted reply | art-platform | 2 | 3 | 4 | 4 | 4 | **17** | S | open |
| Social/newsletter draft buttons | art-platform | 3 | 4 | 2 | 3 | 5 | **17** | S | open |
| Project/metric → article-digest | job-hunter | 2 | 4 | 4 | 4 | 3 | **17** | S | 📋 issue #15 |
| Source → deck (text/url/pdf/photo) | flashkarte | 3 | 5 | 1 | 3 | 4 | **16** | M | open |
| Bulk zip-import AI prefill | art-platform | 1 | 4 | 2 | 4 | 4 | **15** | M | open |
| Contact-form outreach (448 leads) | artcrm (→3) | 2 | 4 | 2 | 3 | 4 | **15** | M | open |
| URL → summarized note | notes-world | 3 | 3 | 2 | 4 | 3 | **15** | M | open |
| AI-populated checklists | notes-world | 2 | 2 | 1 | 3 | 4 | **12** | S | open |

**Axes:** Freq = how often the chore fires · Avoid = how often you *skip* it because it's annoying (hidden value) · Drift = does the manual version go stale/wrong with downstream cost · Mech = how cleanly the plumbing splits from the judgment · Reuse = how much it borrows the engcrm parts-bin (lower build cost).

### What the data surfaces (yours to ponder)
- **Painting auto-catalogue tops it** — strong on all five, low effort. The flagship.
- **Best value-per-effort: re-enable the reply-drafter** — a 20 for *XS* work, because it's already built.
- **flashkarte "source→deck" dropped to 16** — the rubric docks it: no drift (decks don't go stale) and the card-generation carries real judgment (what deserves a card), so it's a weaker mechanical split than my gut rated it. Honest correction.
- **The avoidance column lights up the things you quietly skip** — voice capture, blog/social writing, tagging, signatures, the missing article-digest. That's value invisible to a time estimate.
- **Effort clusters at the top** — the top seven are all XS/S. The sweet spot is dense; you don't have to trade leverage for effort here.

---

## Tier 1 — do first (high leverage · tiny effort · max reuse)

| # | App | Opportunity | Why it's #1-tier | Effort |
|---|-----|-------------|------------------|--------|
| 1 | **artcrm** (→ all 3 CRMs) | **Turn the inbound-reply drafter back on** | The classify + draft-reply code is *fully built* (`followup-agent/graph.py` 251–269) but the supervisor **short-circuits it** ("Currently disabled"). A positive gallery reply is the highest-value moment in the funnel. Re-enabling = drafts land in the approval queue you already use. | **XS** (config) |
| 2 | **art-platform** | **Photograph a painting → AI fills the catalogue** | The card reader, pointed at your core product object. Upload form needs only a title; descriptions/alt-text/medium/style usually left blank → thin site + weak social posts. Vision drafts all 14 fields at the moment of highest context. Saves 5–15 min/painting. | **S** |
| 3 | **notes-world** | **Auto-tag + type + due-date at capture** | Every quick-capture lands as "Untyped, no tags" → you enrich it later, context lost. The Haiku classifier *already exists* in the markdown importer — wire it to the capture bar as dismissable suggestions. | **S** |
| 4 | **job-hunter** | **Recruiter email → status update** + **LinkedIn screenshot → pipeline** | The pipeline is otherwise fully automated; these are the two manual gaps. Stale statuses break the follow-up cadence. LinkedIn (login-walled) is the *only* source the URL-fetch can't handle — a screenshot + vision fixes it. | **S** each |

---

## Tier 2 — high value · S–M effort (mostly porting engcrm's voice/vision)

| # | App | Opportunity | Notes | Effort |
|---|-----|-------------|-------|--------|
| 5 | **notes-world / flashkarte / art-platform** | **Voice capture, ported** — speak → item (notes), → deck (flashkarte), → blog post (art-platform) | One pattern (engcrm's `/api/voice` + Voice Entry screen + the live Whisper box), three apps. | S–M each |
| 6 | **flashkarte** | **Source → deck** — paste/drop text, a URL, a PDF, or a photo → AI generates SM-2 cards | The product's whole reason to exist. The MCP `create_deck`/`add_cards` tools already work; the gap is an **in-app "generate from source"** surface so you don't leave the app. | M |
| 7 | **notes-world** | **Photo/whiteboard → note** (vision) and **forward-email → task** (mail-mcp already reads the inbox) | You write on paper + whiteboards daily; mail-mcp is already deployed. | M each |
| 8 | **artcrm** (→ all 3) | **`maybe`-pile AI re-review**, **post-visit digest → follow-up drafts**, **email-signature → contact enrichment** | The scout's `score_gallery_prompt` reused verbatim; the migration-009 visit fields (`last_impression`, `followup_promised`, `decision_maker`) are currently **write-only dead data** — #5 reads them back. | S–M |

---

## Tier 3 — solid · M effort · more situational

| # | App | Opportunity | Effort |
|---|-----|-------------|--------|
| 9 | **art-platform** | Bulk onboarding: drop a folder of images → AI-drafted catalogue CSV (kills the 28-column hand-prep); inquiry → AI-drafted reply; social-caption + newsletter draft buttons (the `PostFormatter`/`draft-newsletter` logic already exists, just not surfaced in-app) | M / S |
| 10 | **artcrm** (→ all 3) | Contact-form outreach for the **448 cold contacts with a website but no email** — currently skipped; draft + form-URL into approvals | M |
| 11 | **notes-world** | URL/article → summarized note; AI-populated checklists (groceries/packing) | M / S |
| 12 | **job-hunter** | Project/metric capture → `article-digest.md` proof points (feeds every evaluation/PDF/cover letter; file currently missing) | S |

---

## Cross-cutting themes (the same four shapes repeat everywhere)

1. **Vision capture** (photo → structured data): painting catalogue · whiteboard→note · textbook→deck · LinkedIn→job. → the card reader, four more times.
2. **Voice capture** (speak → structured): note · deck · blog post. → the engcrm voice feature, ported.
3. **AI-draft-reply behind the approval gate**: gallery replies · buyer inquiries · recruiter emails · email→task.
4. **"Make structured X from a raw source"**: deck-from-anything · catalogue-from-images · note-from-URL.

---

## Recommended sequence

- ✅ **Done 2026-06-24:** re-enable CRM reply drafting, and forward-email→task. Capture-tagging turned out already-built; job-hunter trio moved to `johnfire/job-hunter` issues #13–15.
- **Next up (the flagship):** painting → auto-catalogue (art-platform, 22/25 — vision already proven in the engcrm card reader).
- **Then (the force-multiplier):** voice-capture port — one build, three apps (notes-world / flashkarte / art-platform).
- **Backfill:** the artcrm `maybe`-pile / post-visit / signature trio; flashkarte source→deck; art-platform inquiry + social/newsletter buttons.

The whole list is still a few S/M features, not a rewrite — because engcrm already paid the infrastructure cost. Per-app full detail is in each researcher's findings (this doc is the synthesis).
