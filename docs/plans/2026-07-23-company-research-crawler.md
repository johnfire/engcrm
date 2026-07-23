# Improvement: evidence-led company research crawler

## Outcome

Improve lead research so that each candidate is researched from the most relevant
public sources rather than from a small, arbitrary set of search results. The
system should reliably read a company's own website, identify publicly named
professional contacts, collect only relevant background context, and give Scout
and Outreach a compact, source-backed dossier.

This is a proposal only. It does not change the current research pipeline,
contact records, or outbound-email behaviour.

## Why improve the current flow

The current pipeline already has useful primitives:

- Google Places / geographic search discovers businesses.
- DuckDuckGo supplements discovery and enrichment.
- `gcrm.tools.fetch_page` uses Bright Data Web Unlocker when configured and
  falls back to an SSRF-protected HTTP fetch.
- Research fetches up to three distinct result URLs, while enrichment fetches
  candidate result URLs before extraction.

This has two limitations:

1. A high-ranking result is not necessarily the official company website.
2. The fetch does not intentionally visit the pages most likely to contain
   useful evidence: About, Team, Contact, Imprint, Services, Portfolio, and
   recent News pages.

The result is uneven company context, missed named contacts, and LLM decisions
that cannot always point back to a specific source.

## Proposed research flow

```text
search engine + Places data
          |
          v
rank and verify candidate domains
          |
          v
crawl a small approved page set on the official domain
          |
          v
extract company facts and public professional names
          |
          v
run limited contextual searches for verified names
          |
          v
write an evidence-led company dossier
          |
          +--> Scout: fit evaluation
          +--> Outreach: personalisation evidence (still approval-gated)
```

### 1. Discover and rank links

Use the existing search backend initially. Rank each returned URL before fetching:

1. exact official-domain match from Google Places or an existing contact website;
2. company-name plus city match;
3. relevant professional sources (industry bodies, exhibition programmes,
   reputable local press);
4. lower priority: directories and review sites.

Reject or heavily down-rank social networks, data brokers, unrelated same-name
businesses, and search-result pages. A selected domain must pass the existing
public-URL / SSRF protections.

### 2. Read the official company website deliberately

Begin with the landing page and map same-domain links. Fetch no more than 5–8
pages per company, prioritising:

- home;
- about, team, people, or founders;
- contact and legal notice / imprint;
- services, portfolio, programme, exhibitions, or clients;
- one recent news or event page where relevant.

Only crawl the verified company domain by default. Do not recursively crawl
external links, forms, account-only areas, or media assets. Cache successful
results using the canonical URL and content hash to avoid repeat requests.

### 3. Research a named person carefully

Only research a person when their name and professional role appear on the
company's own public site (or an equally authoritative professional source).
Use one narrow query such as `"Full Name" "Company Name" City` and collect only
context relevant to the business relationship: role, publicly presented work,
professional affiliation, and credible public coverage.

Do not search for private-life information, scrape personal social accounts,
infer sensitive traits, or use information to make automated decisions about a
person. Never treat an ambiguous name match as confirmed; retain it as an
unconfirmed lead or discard it.

### 4. Produce a compact dossier

Persist a structured, bounded research result rather than full copies of web
pages. Each assertion must contain its source URL and retrieval time.

Suggested fields:

| Field | Purpose |
| --- | --- |
| `company_summary` | Short factual description of the company and its offer |
| `official_domain` | Domain selected by the verification step |
| `evidence` | Source URL, title, retrieval time, excerpt/hash, and source type |
| `people` | Verified name, public role, source URL, and confidence |
| `person_context` | Relevant professional context with an explicit source |
| `research_status` | complete, partial, blocked, or no-authoritative-source |
| `research_version` | Extraction policy/prompt version used for reproducibility |

The LLM receives only curated evidence. Prompts should require it to label
claims as either *confirmed by the company site* or *third-party indication*;
it must not invent personalisation details when evidence is absent.

## Technology recommendation

Use **Crawl4AI** as the first implementation option behind a small internal
adapter. It is suitable because it provides asynchronous, browser-based page
retrieval, clean Markdown extraction, link discovery, content filtering,
caching, and an optional `robots.txt` check. It should materially improve
coverage of JavaScript-rendered company sites compared with the current HTML
stripping fallback.

Keep an interface such as `CompanyResearchFetcher` so the rest of the agents do
not depend on Crawl4AI directly. This preserves these options:

- Crawl4AI as the default self-hosted crawler;
- the existing Bright Data / HTTP fetch as a fallback for individual pages;
- Playwright-only implementation if we later want lower-level browser control;
- a managed API only after a separate processor, cost, retention, and transfer
  review.

Do not use a managed crawler as the default merely for convenience. Sending
candidate URLs, contact-related context, or fetched content to another provider
is a data-processing and transfer decision.

## Guardrails

### Technical

- Preserve `fetch_page` SSRF protection for initial and redirected URLs.
- Respect `robots.txt` where enabled and do not bypass access controls,
  CAPTCHAs, paywalls, or login walls.
- Apply per-domain concurrency, request delay, timeout, maximum page count, and
  a per-contact crawl budget.
- Do not load scripts, images, or downloads unless required for safe text
  rendering; strip tracking parameters and canonicalise URLs.
- Isolate failures: a blocked site or person-search error produces a partial
  dossier and never fails the complete research run.
- Log request/correlation ID, contact ID, source URL, crawler outcome, policy
  version, and a bounded error code. Do not log page bodies or unnecessary
  personal details.

### Data protection and outreach policy

Public business contact details and public professional names can still be
personal data. This feature must remain subject to the project's existing GDPR
findings, especially the open Art. 14, retention, lawful-basis, processor, and
international-transfer work. It is not a compliance determination.

Before enabling it for production leads, define and implement:

- a purpose limitation: B2B relevance research and human-reviewed outreach
  only;
- data minimisation and a short retention schedule for uncontacted people and
  research evidence;
- erasure/opt-out propagation to dossier and person records;
- source/provenance and decision logging;
- human review before first contact (the existing approval queue remains the
  required gate);
- documented provider assessment for Crawl4AI deployment and any fallback or
  LLM provider that receives the data.

## Delivery plan

1. **Foundation** — define dossier schema, `CompanyResearchFetcher` protocol,
   safe URL/domain policy, cache abstraction, and unit tests.
2. **Crawler adapter** — add Crawl4AI implementation with `robots.txt`,
   same-domain scope, page cap, timeout, and Bright Data/HTTP fallback.
3. **Evidence extraction** — rank links, select pages, extract company facts
   and named roles, and store explicit source provenance.
4. **Person context** — add opt-in, single-query contextual search with strict
   identity matching and no sensitive/private-source policy.
5. **Agent integration** — enrich research and Scout inputs from the dossier;
   Outreach may use only cited facts in drafts.
6. **Controlled rollout** — feature flag disabled by default, test on a small
   manual cohort, assess cost/success/false-match rates, then enable per agent.

## Acceptance criteria

- For a company with a valid official website, the dossier includes the official
  domain and at least one source-backed company summary.
- The crawler never follows links outside the approved domain during company
  exploration and never fetches unsafe/private-network addresses.
- A named person is stored only when name and role are attributable to a source;
  ambiguous matches are not promoted as facts.
- Every dossier claim used by Scout or Outreach has a source URL and retrieval
  timestamp.
- A blocked, dynamic, or unavailable website records a partial/blocked outcome
  without failing unrelated contacts.
- Existing research, enrichment, scout, and outreach tests remain green, and
  new unit/integration tests cover ranking, SSRF/redirect rejection, page
  limits, robots behaviour, identity ambiguity, provenance, and opt-out/erasure
  handling.
- The feature is disabled unless explicitly enabled by configuration.

## Decisions still needed

- Whether person-context search launches in the first rollout or follows after
  company-only crawling is proven reliable.
- The retention period and legal/process evidence for third-party personal data.
- The authoritative search provider and any budget/rate limits.
- Whether evidence is stored in relational tables, JSONB tied to a contact, or
  an append-only research-event table.
