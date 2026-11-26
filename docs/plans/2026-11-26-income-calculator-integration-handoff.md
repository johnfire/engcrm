# Income Calculator → EngCRM integration handoff

Date: 2026-11-26

Status: ready for implementation; integration has not started

Target repository: `/home/chris/ppp2/engcrm`

Source prototype: `/home/chris/ppp2/income calculator` at commit `d1c1369`

## Mission

Integrate the working German freelancer income calculator into the EngCRM web
application as a private, admin-only page. Preserve its current calculations and
visual clarity while using EngCRM's existing authentication, CSRF protection,
security headers, navigation, translations, templates, deployment and test
infrastructure.

This is deliberately a small integration. The first EngCRM version remains a
manual, unsaved annual estimate. It must not import CRM contracts, alter the
Forecast screen, add database tables, expose a mobile/API feature or attempt to
finish the larger tax-planning product.

## Definition of done

An EngCRM administrator can open `/income-calculator`, enter the same figures as
in the local prototype and compare the same two VAT scenarios. The page looks
at home inside EngCRM, works in English and German, passes all existing and new
tests, and does not save or log the entered financial figures.

The result must retain these boundaries:

- Only authenticated administrators can GET or POST the calculator page.
- Inputs live only for the rendered request/response. There is no database
  migration, cookie storage, browser storage, analytics event or audit payload
  containing the financial values.
- The calculation engine remains pure and independent of FastAPI, sessions and
  database code.
- A POST displays a result on the same page. A refresh/reset may discard it.
- The standalone server in `/home/chris/ppp2/income calculator` is not mounted,
  proxied, imported as a runtime dependency or deployed alongside EngCRM.
- Existing EngCRM routes, Forecast calculations and CRM records are unchanged.
- Work is committed locally on `main`; do not push or deploy until Chris asks.

## Decisions already made for this handoff

| Question | First integration decision |
| --- | --- |
| URL | `/income-calculator` for both GET and POST |
| Access | Admin only, because this is personal financial planning |
| Navigation | Admin dropdown, visible only to administrators |
| Storage | None; retain the prototype's unsaved behavior |
| CRM import | Out of scope; manual entry only |
| Forecast integration | Out of scope; do not read or write the Forecast plan |
| Mobile/API | Out of scope |
| Languages | English and German, using EngCRM i18n keys |
| VAT status | Still unknown; show both Kleinunternehmer and regular-VAT scenarios |
| Tax year | 2026 rules, visibly labelled |
| Tax authority | Planning estimate only, never presented as an assessment |

If Chris later wants persistence or CRM imports, design those as a separate
feature after this integration is working. Do not silently expand this task.

## Read before changing anything

1. `/home/chris/ppp2/engcrm/AGENTS.md`
2. `/home/chris/ppp2/engcrm/README.md`
3. `/home/chris/ppp2/engcrm/gcrm/api/main.py`
4. `/home/chris/ppp2/engcrm/gcrm/api/templates.py`
5. `/home/chris/ppp2/engcrm/gcrm/api/auth.py`
6. `/home/chris/ppp2/engcrm/gcrm/ui/templates/base.html`
7. `/home/chris/ppp2/engcrm/tests/test_nav.py`
8. The source files listed in the next section.

Follow the repository rules: no branch, tests first, never weaken a failing
test, commit locally when finished and wait for a separate push instruction.
Preserve any unrelated working-tree changes.

## Source prototype inventory

The prototype is working and tested. Use it as the behavior oracle, not as a
second web service.

| Source file | What to reuse |
| --- | --- |
| `src/income_calculator/tax/income_2026.py` | Pure 2026 single-assessment income-tax tariff and solidarity calculation |
| `src/income_calculator/tax/vat.py` | Pure VAT scenarios, enums and cent-safe calculations |
| `src/income_calculator/tax/quick_estimate.py` | Pure input/output dataclasses and annual estimate calculation |
| `src/income_calculator/web/app.py` | Form model, comma/decimal normalization and request behavior; do not reuse its FastAPI app |
| `src/income_calculator/web/templates/quick.html` | Field order, explanations, result hierarchy and warning copy |
| `src/income_calculator/web/static/quick.css` | Visual reference; do not paste its global selectors into EngCRM |
| `tests/unit/test_estimate.py` | Income-tax, solidarity and grant invariants |
| `tests/unit/test_vat.py` | VAT scenario invariants and threshold examples |
| `tests/integration/test_quick_web.py` | Form/result behavior and regression cases |
| `README.md` | Current product limitations and local-preview behavior |

The source commit already includes the Gründungszuschuss field. Do not integrate
from an older calculator commit.

## Target file map

Use this layout unless the current repository has materially changed:

| Target file | Action |
| --- | --- |
| `gcrm/income_calculator/__init__.py` | New package marker; export only the small public calculation surface if useful |
| `gcrm/income_calculator/income_2026.py` | Copy/adapt the pure tariff functions |
| `gcrm/income_calculator/vat.py` | Copy/adapt the pure VAT model |
| `gcrm/income_calculator/estimate.py` | Copy/adapt `quick_estimate.py` and update imports |
| `gcrm/income_calculator/form.py` | Move the Pydantic form model and conversion into a testable boundary module |
| `gcrm/api/routers/income_calculator.py` | New admin-only GET/POST router |
| `gcrm/ui/templates/income_calculator.html` | EngCRM template extending `base.html` |
| `gcrm/ui/static/style.css` | Add calculator styles, fully scoped under the calculator page class |
| `gcrm/api/templates.py` | Add a cent-to-euro Jinja filter if the template needs one |
| `gcrm/api/main.py` | Import and include the new router |
| `gcrm/ui/templates/base.html` | Add the admin-only navigation link |
| `gcrm/i18n/en.json` | English navigation, field, result, error and warning strings |
| `gcrm/i18n/de.json` | German equivalents for every new user-visible string |
| `tests/test_income_calculator_math.py` | Port the pure calculation tests |
| `tests/test_income_calculator_web.py` | Add form, auth, CSRF, rendering and preservation tests |
| `tests/test_nav.py` | Extend expected admin navigation and active-state cases |

Do not add a database migration or modify `pyproject.toml` merely for this
feature. EngCRM already uses FastAPI, Jinja, multipart forms and Pydantic.

## Required architecture

Keep the flow one-directional:

```text
browser form
    ↓
admin-only EngCRM router
    ↓ parse and validate
IncomeCalculatorForm
    ↓ convert euros to integer cents
EstimateInputs
    ↓ pure functions
VAT scenarios + 2026 tax estimate
    ↓ immutable Estimate values
EngCRM Jinja template
```

The files under `gcrm/income_calculator/` must not import FastAPI, Jinja,
sessions, authentication, database helpers or templates. The router may import
the engine, but the engine must never import the router.

All money entering the engine is integer cents. Decimal input is accepted only
at the form boundary. Never introduce binary floating-point arithmetic for
money.

## Form contract

Preserve these field names so the prototype tests and user expectations map
cleanly to EngCRM:

| Field | Meaning | Calculation role |
| --- | --- | --- |
| `consulting` | Annual consulting or other taxable sales | VAT scenario and business revenue |
| `amount_basis` | `gross_customer_total` or `net_fee` | Whether 19% VAT is inside or added to consulting amount |
| `education` | Teaching income provisionally assumed VAT-exempt | Receipts and revenue, not output VAT |
| `startup_grant` | Annual Gründungszuschuss | Cash only; not sales, VAT or taxable income |
| `expenses` | Business costs actually paid/planned, including VAT | Reduces disposable cash |
| `business_deduction` | Expected deductible business costs | Reduces business profit/taxable income |
| `health_costs` | Health/care insurance cash paid | Reduces disposable cash |
| `health_deduction` | Adviser/user estimate of deductible health/care insurance | Reduces taxable income |
| `pension_costs` | Pension cash paid | Reduces disposable cash |
| `pension_deduction` | Adviser/user estimate of deductible pension contribution | Reduces taxable income |
| `medical_costs` | Out-of-pocket medical cash costs | Reduces disposable cash |
| `medical_deduction` | Eligible amount after personal threshold | Reduces taxable income |
| `disability_allowance` | Behinderten-Pauschbetrag | Reduces taxable income; never cash or a tax credit |
| `paid_tax` | Income tax already paid | Shown against remaining tax; never subtracted twice |
| `months_remaining` | Divisor from 1 through 12 | Divides full annual remainder for display |
| `church_rate` | 0, 8 or 9 percent | Percentage of calculated income tax |

Money fields accept blank, comma-decimal or point-decimal non-negative amounts
with at most two decimal places. Blank means zero. Keep the prototype ceiling
of €10,000,000 per field unless there is a written reason to change it.

Return HTTP 422 and re-render the entered values when validation fails. Do not
clear the form on an error. The visible message should be useful but must not
echo a traceback or internal validation structure.

## Calculation invariants: do not “simplify” these

### VAT scenarios

The calculator does not know Chris's confirmed VAT registration. It therefore
returns two clearly labelled scenarios:

1. Kleinunternehmer
2. Regular VAT

Teaching income is provisionally treated as exempt under §4 no. 21 UStG.
Consulting is treated as taxable at 19% under the regular-VAT scenario.
`amount_basis` determines whether the entered consulting amount is the customer
total including VAT or the fee before VAT.

The current §19 threshold implementation is provisional. It uses the entered
taxable sale amounts in their supplied order, with €25,000 as the prior-year
limit and €100,000 as the current-year ceiling. Do not rewrite that logic or
claim it settles legal eligibility during this integration. Preserve the visible
warning that the VAT status and educational exemption need adviser confirmation.

### Annual tax estimate

For each VAT scenario:

```text
business profit
  = revenue excluding output VAT
  - deductible business expenses

estimated taxable income
  = max(0, business profit - personal deductions)

estimated total tax
  = income tax + solidarity surcharge + church tax

annual remainder
  = customer receipts
  + Gründungszuschuss
  - output VAT
  - business cash costs
  - personal cash costs
  - estimated total tax

remaining tax to pay
  = max(0, estimated total tax - tax already paid)

selected-month figure
  = annual remainder / months_remaining
```

`paid_tax` does not increase the annual remainder. The total annual tax has
already been subtracted there; the paid amount is only used to show how much of
that liability may remain.

### Gründungszuschuss

The current field means the Gründungszuschuss under §93 SGB III, not an arbitrary
startup grant. For this estimate it:

- increases cash available;
- is not customer revenue;
- is outside the VAT calculation;
- does not increase taxable income, income tax, solidarity surcharge or church
  tax; and
- does not alter either VAT scenario.

The legal label should say this treatment applies specifically to the §93 SGB
III benefit. §3 no. 2 EStG expressly lists the Gründungszuschuss as tax-free;
the benefit is not listed in the §32b EStG progression-reserve benefits. Keep
the overall “planning estimate, not tax advice” warning.

Official references:

- <https://www.gesetze-im-internet.de/sgb_3/__93.html>
- <https://www.gesetze-im-internet.de/estg/__3.html>
- <https://www.gesetze-im-internet.de/estg/__32b.html>

### Known omissions that must remain visible

The first integrated page still does not calculate:

- input VAT recovery;
- verified §19 eligibility or precise turnover timing;
- verified educational VAT exemption for each contract;
- the Übungsleiter allowance;
- other employment, pension, investment or rental income;
- loss carryforwards;
- the medical-cost personal threshold;
- quarterly payment timing or official Finanzamt prepayment schedules;
- cash already withdrawn or spent earlier in the year; or
- a true remaining-month safe-to-spend amount.

Do not silently fill these gaps with guesses.

## Router implementation

Create an `APIRouter` whose dependencies contain `Depends(require_admin)`.
This is stricter than the common read-for-everyone/write-for-admin pattern used
on some EngCRM pages; both GET and POST contain private personal finance data.

Recommended shape:

```python
router = APIRouter(
    prefix="/income-calculator",
    tags=["income-calculator"],
    dependencies=[Depends(require_admin)],
)
```

The GET handler renders defaults with no estimates. The POST handler reads the
form, validates it, calculates the estimates and renders the same template with
the entered values intact.

Use the shared `templates` object from `gcrm.api.templates`. It automatically:

- injects the active English/German translator;
- injects EngCRM's CSP nonce;
- inserts CSRF tokens into HTML POST forms;
- sets private, no-store cache headers; and
- provides the existing `eur` money formatter.

Do not instantiate another `Jinja2Templates`, mount another static directory,
add another `SessionMiddleware`, disable CSRF or add inline JavaScript/styles.

If the immutable result values stay in integer cents, add a shared filter such
as:

```python
def cents_eur(value: int) -> str:
    return eur(Decimal(value or 0) / Decimal(100))
```

Register it once in `gcrm/api/templates.py`. Test negative, zero, whole-euro and
cent values. Do not divide cents with a float in Jinja.

Import the router in the grouped router import in `gcrm/api/main.py`, then call
`app.include_router(income_calculator.router)` beside the other HTML routers.

## Template and visual integration

`income_calculator.html` must extend `base.html`; it must not reproduce the HTML
document, top navigation, font imports or body shell from the standalone page.

Use:

```jinja2
{% extends "base.html" %}
{% block title %}{{ t('incomeCalculator.title') }} — {{ t('nav.brand') }}{% endblock %}
{% block main_class %}income-calculator-page{% endblock %}
```

Preserve the prototype's useful visual hierarchy:

- short introduction and 2026 badge;
- prominent work-in-progress/tax-assumption notice;
- annual inputs grouped by Income, Costs & deductions, Medical/disability and
  Planning;
- two side-by-side scenario cards on wider screens;
- annual remainder as the dominant result;
- selected-month amount immediately below it;
- detailed receipt, VAT, profit, taxable-income and tax rows;
- explanation and limitations after the scenarios; and
- one-column layout on narrow screens.

Do not copy `quick.css` verbatim. It contains global `:root`, `body`, heading,
input, button and definition-list rules that would restyle the entire CRM.
Translate the design into selectors scoped beneath `.income-calculator-page`
and use `income-calculator-*` class names where a rule might collide. Append
the scoped rules to EngCRM's existing `gcrm/ui/static/style.css` so the existing
cache-busting mechanism continues to work.

Retain EngCRM's nav and base page spacing. Reuse existing colors and button
classes where practical, but preserve the calculator's readable green scenario
cards and distinct warning panel. Color must not be the only carrier of meaning.

Every input needs a real `<label for=...>`, visible focus state, appropriate
`inputmode`, and accessible error text. Results should use semantic headings and
definition lists or tables. The result region should have `aria-live="polite"`.

## Navigation and translations

Because the page is admin-only, add it to `admin_tabs` only inside the existing
admin-role condition in `base.html`. Recommended entry:

```jinja2
{'href': '/income-calculator', 'prefix': '/income-calculator', 'label': t('nav.incomeCalculator')}
```

Add `nav.incomeCalculator` and every page string to both `en.json` and `de.json`.
Do not hard-code an English-only page. Preserve legal references such as
“Gründungszuschuss”, “Kleinunternehmer”, “§93 SGB III” and statute numbers in
both languages.

Update `tests/test_nav.py` for:

- the new admin-only link and href;
- the `/income-calculator` active state;
- absence from spectator navigation; and
- unchanged alphabetical ordering of top-level navigation in both languages.

The link belongs in the Admin dropdown, not the top-level list, so the expected
top-level ordering should not change.

## Test-first build order

### 1. Establish the baseline

Before edits:

```bash
cd /home/chris/ppp2/engcrm
git status --short
uv run pytest tests -q -m "not integration and not e2e and not network"
uv run ruff check .
```

Record any pre-existing failure. Do not hide, delete or skip it.

Also confirm the source oracle still passes:

```bash
cd "/home/chris/ppp2/income calculator"
uv run pytest -q
```

### 2. Port pure tests first

Copy/adapt the prototype's VAT and estimate unit tests into
`tests/test_income_calculator_math.py`. Run them before adding the engine and
observe the expected import failure. Then port the engine with import paths
changed from `income_calculator.*` to `gcrm.income_calculator.*`.

Do not edit expected values merely to make the port pass. If behavior differs
from source commit `d1c1369`, stop and explain the difference.

### 3. Write web tests before the route

`tests/test_income_calculator_web.py` should cover at least:

1. Anonymous GET redirects to `/login`.
2. A non-admin authenticated role receives 403.
3. Admin GET returns 200 and shows every field.
4. Admin POST with valid input shows both VAT scenarios.
5. Comma and point decimal inputs behave identically.
6. Negative, malformed or over-precision input returns 422.
7. A validation error preserves all entered form values.
8. Health, pension and medical cash costs reduce cash, while their deduction
   fields affect taxable income.
9. The disability allowance reduces taxable income but not cash directly.
10. Tax already paid changes “remaining tax” without changing annual remainder.
11. Months must be 1–12 and divide the full annual remainder.
12. Gründungszuschuss is shown separately and changes only disposable cash.
13. The response carries EngCRM's private/no-store and security headers.
14. A genuine browser POST without a valid CSRF token is rejected.
15. English and German pages render the translated title, warnings and primary
    field/result labels.

Use dependency overrides only where the test is about page behavior rather than
the auth implementation. Keep at least one real auth-boundary test with no
override.

### 4. Implement form, router and template

Make the smallest code change that satisfies the new tests. Keep parsing in the
form model, calculations in the engine, request orchestration in the router and
presentation in the template.

### 5. Add navigation and CSS

Extend the existing navigation tests before changing `base.html`. Add scoped
CSS and test for any critical selector or layout contract that has previously
regressed.

### 6. Mutation check

The repository does not currently configure a mutation-test runner. Perform at
least one controlled mutation of the new core path: temporarily change the
Gründungszuschuss addition to subtraction, or allow it to enter taxable income.
The focused test must fail. Restore the code and rerun the focused test. Do not
commit the mutation.

## Fixed reference cases

These are guardrails, not optional examples.

### Grant-only case

Input:

```text
startup_grant = €10,000
everything else = €0
months_remaining = 12
```

Both scenarios must show:

```text
customer receipts = €0
Gründungszuschuss = €10,000
taxable income = €0
total tax = €0
annual remainder = €10,000
```

### Grant isolation case

Calculate a baseline and then add a €10,000 grant. In both VAT scenarios:

- receipts are unchanged;
- output VAT is unchanged;
- revenue and profit are unchanged;
- taxable income and all taxes are unchanged; and
- annual remainder increases by exactly €10,000.

### Gross consulting case

With €75,000 entered as a gross customer total under regular VAT, revenue before
business deductions is €63,025.21 and output VAT is €11,974.79. Preserve the
prototype's cent rounding.

### Cash versus deduction case

A €1,000 medical cash cost with only €200 entered as deductible must reduce cash
by €1,000 but taxable income by only €200. The disability allowance is another
deduction and must not be subtracted as cash.

Port the remaining exact VAT/tax boundary assertions from the source tests.

## Verification commands

Run from `/home/chris/ppp2/engcrm`:

```bash
uv run pytest tests/test_income_calculator_math.py -q
uv run pytest tests/test_income_calculator_web.py tests/test_nav.py tests/test_browser_headers.py -q
uv run pytest tests -q -m "not integration and not e2e and not network"
uv run ruff check .
```

If a disposable real PostgreSQL test database is configured, also run:

```bash
uv run pytest tests/integration -q
uv run pytest tests/e2e -q
```

The existing `tests/e2e/test_every_page_renders.py` discovers GET routes, so the
new route should automatically join the real-schema smoke test. Do not add it to
the skip list.

Start EngCRM locally using the repository's documented command, log in as an
administrator and visually check:

- default empty state;
- the €10,000 grant-only case;
- a mixed consulting/teaching/cost case;
- validation errors with preserved values;
- English and German;
- keyboard focus and labels;
- desktop two-column scenarios; and
- narrow/mobile one-column layout.

Inspect the browser response headers and verify that the POST form contains an
injected CSRF token. Confirm that no financial values appear in server logs,
audit records, URL query parameters or browser storage.

## Security and privacy traps

- Do not make the page public merely because the standalone preview was bound to
  localhost.
- Do not put figures in GET query strings, redirects or log messages.
- Do not log Pydantic validation payloads containing form values.
- Do not add JavaScript persistence, localStorage or autosave.
- Do not bypass the shared template renderer; that would lose CSRF injection,
  CSP nonce handling and no-store headers.
- Do not expose a JSON endpoint in this first version.
- Do not send calculator data to an LLM or third-party service.
- Do not add a database table “for later.” No persistence is part of the privacy
  contract for this milestone.
- Do not weaken EngCRM's CSP with inline script or style allowances.

## What not to do

- Do not run the standalone calculator on another production port.
- Do not copy its `FastAPI()` object, middleware, static mount or launcher.
- Do not add the source directory to `PYTHONPATH` or make it a path dependency.
- Do not rewrite the tax formulas while integrating them.
- Do not merge the calculator with Forecast calculations yet.
- Do not infer annual consulting income from contracts or deals yet.
- Do not save personal tax inputs to CRM tables.
- Do not rename existing EngCRM Forecast concepts to fit the calculator.
- Do not claim the output is a tax return, tax assessment or safe-to-spend cash.
- Do not push, deploy or close unrelated issues without explicit authorization.

## Later phases, explicitly not part of this task

Once the manual integrated page is trusted, a separate design can consider:

1. importing booked/expected EngCRM contract income with a review screen;
2. mapping each contract to gross/net and VAT treatment;
3. monthly and quarterly cash timing;
4. official Finanzamt prepayments versus recommended reserves;
5. saved scenarios with encryption, ownership and deletion/export handling;
6. adviser-confirmed tax settings and year-versioned rules; and
7. a dedicated mobile view if it is genuinely useful.

Each later phase needs its own data model, privacy decision and tests. This
handoff intentionally delivers none of them.

## Completion report expected from the implementing model

When finished, report:

- the route and access policy implemented;
- files added and modified;
- which source commit was ported;
- tests run and exact results;
- whether real integration/e2e suites were available;
- visual/browser checks performed;
- the local commit hash;
- confirmation that nothing was pushed or deployed; and
- any assumption or formula that still needs the tax adviser.

Also prepend the required EngCRM project-status entry in Notes World. Keep the
existing history intact.
