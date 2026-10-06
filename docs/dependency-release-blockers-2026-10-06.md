# Dependency release blockers — 2026-10-06

The backend and Android release workflows for photo-capture commit `4a9d14f`
failed their dependency audits. This change fixes both blockers without changing
CI thresholds or suppressing advisories.

## Changes

- Upgrade `langgraph-sdk` from 0.4.2 to 0.4.6 and constrain future resolutions
  to >=0.4.4. The SDK advisory concerns action-scoped authorization decorators:
  [CVE-2026-104873](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-fvww-7h3r-vfhp).
- Override `shell-quote` to ^1.12.0, updating the lock from 1.10.0 to 1.12.0.
  This fixes its critical command-injection advisory:
  [CVE-2026-102422](https://github.com/advisories/GHSA-pqg4-j6r4-53mv).
- Add regression tests for action-scoped authorization and quoting line
  terminators after comments. No shell command is executed by these tests.
- Correct the existing i18n account fixture to mock its token-version lookup.
  Previously, four tests returned 401 because their mocked account was checked
  against the real database. Add missing-account and revoked-token cases that
  still require 401 and verify no language update or push occurs.

Only the two affected dependency versions change. Expo, React Native and the
other Python package versions remain unchanged.

## Local validation

Validated in an isolated archive of the repository with fresh locked installs
and a disposable migrated PostgreSQL 16 database:

- Backend `pip-audit`: zero known vulnerabilities; local project packages are
  skipped by the auditor because they are not published on PyPI.
- Mobile `npm audit --omit=dev --audit-level=critical`: passes; zero critical
  vulnerabilities. 55 high and 14 moderate findings remain outside this fix.
- Ruff, mobile TypeScript and ESLint: pass.
- Backend: 1,164 tests pass with the existing network exclusion (one deselected).
- Agent packages: 51 tests pass across all six suites.
- Mobile: 244 tests pass across 33 suites. After adjusting the new test import
  for ESLint, its five regression cases, TypeScript and ESLint pass again.
- Expo Android export: passes and emits the Hermes bundle.

The older photo-capture report's four i18n failures are resolved by this change.
Live CI, APK publication and backend deployment require pushing this commit;
local validation does not establish deployment success.
