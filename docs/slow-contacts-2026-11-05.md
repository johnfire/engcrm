# Contacts page slowdown — 5 November 2026

The slowdown was reproduced in production with read-only queries. Public login
and static assets responded in 0.03–0.10 seconds, and the server had spare CPU
and memory. The delay was in the workspace-scoped Contacts query.

PostgreSQL's JIT compiler tried to compile 1,659 functions for the combined
Contacts query, including its nested row-security checks. The estimated plan
cost was 1,672,874.73, enough to enable compilation, inlining and optimization.
A scoped execution took 39.8 seconds before a configured 15-second statement
timeout could cancel it. With JIT off in a separate read-only transaction, the
same query returned 50 rows in 0.176 seconds.
Rendering the full page against the live data in a read-only process took
0.403 seconds for All offers and 0.601 seconds for Consulting with JIT off.

Workspace-scoped connections now issue `SET LOCAL jit = off`. This avoids the
compilation overhead while preserving the restricted role and all row-security
policies. The setting belongs to that transaction; maintenance/operator
connections retain their existing setting. It does not change production
database configuration or weaken access checks.

`tests/integration/test_request_query_compilation.py` checks the real database
setting and role, verifies that the Contacts plan has no JIT section even with
its cost threshold forced to zero, and checks that an operator connection keeps
its original setting. Both regression tests failed before the fix.
