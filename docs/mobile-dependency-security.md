# Mobile dependency remediation — 6 November 2026

The lockfile remains on Expo SDK 56 and React Native 0.85. Security and compatible
patch updates were installed, including Expo 56.0.24, Expo Router 56.2.22,
Node Forge 1.4.3 and the supported SDK 56 asset/screens dependencies.

Fresh public-registry scans of the before/after lockfiles report:

| Inventory | High | Moderate | Low | Critical | Total |
| --- | --- | --- | --- | --- | --- |
| Before | 7 | 18 | 9 | 0 | 34 |
| After | 3 | 0 | 14 | 0 | 17 |

These are affected-package counts, including parent chains, not independent
vulnerabilities. Two advisory causes remain: the high Zod CLI finding and the
low deepmerge tooling finding described below. They have not been erased from
the inventory or called patched.

## Fixed and verified

- `decode-uri-component` is overridden to **0.5.1**, fixing both denial-of-service
  advisories. Expo Router still uses CommonJS `query-string` 7.1.3; a two-line
  `patch-package` compatibility patch accepts the fixed decoder's ESM default
  export. Clean `npm ci` applies it with `--error-on-fail`. Jest compiles that
  ESM dependency instead of mocking the production decoder.
- `glob` versions 9+ use **14.0.3** and `minimatch` versions 7+ use **11.0.4**.
  Old callback-style Glob 7 / Minimatch 3 consumers keep their compatible APIs.
  This clears the reported moderate file-matching findings.
- Compatible updates clear the Node Forge, UUID and ESLint validator findings.
- An unconstrained audio peer had selected Expo Asset 58 during update. The
  supported Expo Asset **56.0.25** is now a direct dependency; the final production
  bundle and native build confirm SDK alignment.

## Remaining reviewed tooling findings

- **Zod 3.25.76**, GHSA-mrhx-c7xc-m3w5, is required by the Expo 56 development CLI.
  It is absent from the Android JavaScript bundle. The release policy permits
  only this advisory, severity, exact version and installed path, until
  **5 December 2026**. The exception does not cover another copy, advisory,
  version or increased severity. Do not expose the development/MCP server to
  untrusted clients. A compatible upstream validator update remains outstanding.
- **deepmerge 4.3.1**, GHSA-gcqx-w48m-w2h4, is a low finding in Expo configuration
  and Jest tooling, with no newer compatible release available at verification.
  It is absent from the Android bundle too. Recheck upstream and keep build/test
  configuration trusted; this low finding remains open.

`mobile-dependency-policy.json` records the high exception. The CI gate now
checks the complete dependency inventory, blocks unreviewed high/critical
findings, fails on scanner errors and obsolete/expired exceptions, and separately
rejects the reviewed tooling packages if they appear in Android source maps.
Both the test export and the actual release bundle are checked before upload.
This replaces the previous broad `--audit-level=critical` release allowance.

## Validation

- Clean locked installation and reproducible compatibility patch: passed.
- Full mobile suite: **394 passed**; typecheck and lint: passed.
- Decoder/policy tests: **14 passed**. Unicode, spaces, arrays and escaped paths
  retain their behavior; the malformed-input reproduction finishes in a bounded
  child process. The original vulnerable decoder fails that timeout regression.
- Five policy mutations (expiry, version, severity, advisory and bundle presence)
  plus the legacy decoder were detected by the tests.
- Production Android export and Gradle release-JavaScript task: passed. Both
  source inventories contain **1,893 source paths**, with Zod, Node Forge,
  deepmerge, Glob and Minimatch absent.
- Native arm64 Android debug APK: built successfully. No app was published or
  installed on a user's phone during these checks.
- The previously recorded intermittent organization-priority test failed again
  during the full run. Its resolved initial load now flushes within React's async
  `act` boundary; its set/clear assertions remain, and a fetch assertion was added.
  No test was removed, skipped, or given a longer timeout to hide the failure.

Sources: [decoder advisory](https://github.com/advisories/GHSA-qr28-fpjm-wq7f),
[Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5),
[deepmerge advisory](https://github.com/advisories/GHSA-gcqx-w48m-w2h4),
[Expo SDK 56](https://docs.expo.dev/versions/v56.0.0/).
