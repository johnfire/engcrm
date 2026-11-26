# Offline sync rollout and recovery

Offline storage is opt-in per account from Android Settings. The phone checks
that `MOBILE_SYNC_WRITES=true` on its matching server before enabling it.
The build-time `EXPO_PUBLIC_OFFLINE_CACHE=true` flag is also available for
isolated tests; the default production Android build leaves that flag off.
First exercise a disposable account and database. An account that has already
activated offline storage continues to open and synchronize its own encrypted
cache after a later build switches the flag off. Its workspace, account and
server environment are checked again before opening the cache.

The server defaults both `MOBILE_SYNC_WRITES` and `MOBILE_SYNC_DRAIN` to false.
For a pilot, set both to true on the pilot server. Keep `MOBILE_SYNC_DRAIN=true`
until every device's pending and failed edits have been resolved, including
devices that may have been offline. A 503 response preserves the phone's queue,
but it does not drain it.

`MOBILE_SYNC_DRAIN` allows mutations from any currently registered, non-revoked
device belonging to the authenticated administrator. It does not distinguish
edits queued before and after a rollout pause and does not block newly
registered devices; it is a recovery path, not a switch that freezes new edits.
Do not treat it as an enrollment or authorization boundary. Never remove a
device's local database, key, draft or queued edit as part of rollout recovery.

Changes against deleted or merged records remain available for web review.
There is no automatic 30-day purge while the retention question remains open;
GDPR erasure still removes the affected personal data.
