# Field mode + talking to Claude from anywhere

Date: 03.11.2026. Status: plan, not started.

## What Chris wants

Out in the field (cold, walking, no free hands) he talks to Claude, in the Claude phone
app, the same way he does at home: "I'm standing outside this company, the owner is Maria,
friendly, call back in two weeks." Claude works out where he is and which business it is,
and puts the organization, the person and the first contact straight into engcrm. No
buttons, no typing.

## How it fits together

```
engcrm phone app ──(field mode on: position every few minutes)──▶ engcrm server
                                                                    │ keeps ONE row:
                                                                    │ latest lat/lng,
                                                                    │ accuracy, time
Claude phone app ──▶ Anthropic cloud ──(HTTPS, secret header)──▶ /mcp on the engcrm server
                                                                    │ tools read that row,
                                                                    │ ask Google Maps, and
                                                                    ▼ write to the database
```

## What we know (checked 03.11.2026)

- Custom connectors work on Pro/Max and are called **from Anthropic's cloud for every
  Claude client, the phone apps included**; the server must be reachable from the public
  internet. Source: support.claude.com, "Get started with custom connectors using remote MCP".
- Personal plans may authenticate a connector with **OAuth, or a fixed request header**
  (an API key / bearer token). Same source.
- Not confirmed: whether a connector can be *added* from the phone app, or only on
  claude.ai in a browser. Plan for adding it once on the web; it then shows up per account.
- Our MCP server (`gcrm/mcp/server.py`, FastMCP) runs today only over stdio, reached by SSH.
  It has pipeline tools but **no tool to add an organization or log an activity**.
- The phone app asks for location only "while in use" and has no background-task package.
  Field mode needs **background location**: the engcrm app sits in the background while
  Chris talks in the Claude app.
- Google Places is already used (Text Search). Finding "what is at this spot" needs the
  **Nearby Search** call of the same API, same key.

## Decisions taken in this plan (say if any is wrong)

1. **One switch, in engcrm's Settings: "Field mode".** Off by default. While on, Android
   shows its usual "EngCRM is using your location" notification, so it can never run
   unnoticed. It turns itself off after 8 hours (a forgotten switch stops by evening).
2. **Only the latest position is stored, never a history.** One row per user, overwritten.
   A position older than **10 minutes** counts as unknown: Claude then asks for the address
   instead of filing a company at the café you left an hour ago.
3. **Security: a long secret token in a request header** to start with (simplest thing that
   is safe), plus Caddy/nginx only passing `/mcp` over HTTPS. The token is stored hashed on
   the server, can be revoked and replaced in one command, and is logged on every call.
   OAuth can replace it later without changing the tools.
4. **Writing tools are narrow.** The remote MCP gets only the field tools below. It does
   *not* get the existing pipeline tools that send email or run agents. Every write is
   audit-logged as "claude-mcp" and can be undone.
5. **Claude reads back before it is done.** The tools return what was saved in one line
   ("Saved Bäckerei Maier, Hauptstraße 12, Landsberg; Maria; follow-up 17.11."), so a
   wrong match is caught in the same breath. Two businesses at one spot: Claude asks
   which one.

## The tools Claude will get

| Tool | Does |
|---|---|
| `where_am_i` | Latest position, its accuracy and age; "unknown" when older than 10 min or field mode is off. |
| `businesses_here(radius_m=60)` | Google Places Nearby Search at that position: name, address, type, distance; each marked if already in engcrm (with its id). |
| `find_organization(query)` | Search engcrm by name or city (to log on an existing one). |
| `add_organization(name, address/place_id, type, notes…)` | Create it (with the Places address and coordinates), refusing duplicates the way the phone does. |
| `add_person(organization_id, name, title, …)` | A person met there. |
| `log_activity(organization_id or person_id, kind, note, attitude, my_read, materials_left, follow_up_promised, follow_up_date, offer)` | The same fields as Log activity on the web and phone. |
| `set_next_step(...)` / `set_ratings(...)` | Next step on a deal; priority and value ratings. |
| `undo_last()` | Take back the last thing this connector saved (soft delete / restore). |

## Steps (one commit each, pushed and checked live)

1. **Server: latest position.** Table `field_location` (user, lat, lng, accuracy, recorded_at),
   `PUT /api/me/location` (JWT, field mode only), `DELETE` when the switch goes off. Tests +
   real Postgres.
2. **Phone: Field mode switch.** Settings toggle; `expo-location` background updates +
   `expo-task-manager`; background-location permission and Android's foreground-service
   notification; auto-off after 8 h; sends at most every 2 minutes or 50 m moved. Needs a
   new app build (background location cannot be tested in jest).
3. **Server: Places Nearby Search** in `gcrm/tools/search.py`, with the field mask kept small
   (cost). Tests with a recorded response.
4. **Server: the field tools** in a new `gcrm/mcp/field.py`, reusing the existing write
   helpers (the same code the phone and web use, so rules and audit stay one place).
   Unit tests + real Postgres, including undo.
5. **Server: remote MCP endpoint.** Streamable-HTTP `/mcp` on the live server, token check,
   rate limit, only the field tools exposed; Caddy/nginx route; token created on the server.
   Check from outside with an MCP client before handing it to Claude.
6. **Connect it:** add the connector on claude.ai (URL + header), check it appears in the
   Claude phone app, then a real walk test: field mode on, stand outside a business, talk.

## Open questions for Chris

- **8 hours** auto-off and **10 minutes** "too old": right numbers?
- Should Claude also be allowed to **move a deal's stage** ("they're a prospect now"), or
  only log and set next steps?
- Is the engcrm phone app installed from an APK (no Play Store)? Background location is
  fine either way, but Play Store would add a review step.

## Risks

- **GPS in town is 10–50 m off**; one building can hold several businesses. Covered by the
  read-back and the "which one?" question, not by trusting the closest result.
- **A public endpoint that can write to the CRM.** Covered by decisions 3 and 4; worth a
  `security-check` run once step 5 is live.
- **Battery.** Field mode only while switched on, and sparse updates.
