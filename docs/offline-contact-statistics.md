# Contact dashboard statistics

People and organizations are distinct within each displayed period. A person or
organization contacted in both October and November counts in each month but
only once in all time. The business start is **1 October 2026, inclusive**;
person timestamps are interpreted in Europe/Berlin. No date-boundary change was
needed: a PostgreSQL regression test covers midnight on the first and repeat
contacts across months.

**Offline contacts** is a separate workspace statistic for activity recorded
elsewhere, such as applications on external sites. Administrators enter the
whole monthly total below the people/organization figures and choose Save.
Entering 37 after 35 saves 37 for that month. Retrying the save does not add it
again. It never creates a CRM person, organization, or interaction.

The current and two preceding dashboard months can be edited, starting in
October 2026. All-time offline contacts sum every saved month since that start,
including older months no longer shown individually. Offline figures apply
across all offers; changing the offer filter does not change them. Spectators
can read these statistics but cannot edit them.

Migration `082_offline_contact_totals.sql` adds the monthly ledger, unique per
workspace/month, with row security and bounded nonnegative counts. Changes use
the existing browser CSRF protection and audit identity/correlation IDs. If
offline statistics cannot be read, editing is hidden and an error is shown;
the contact list remains available. Failed saves return an explicit error.
