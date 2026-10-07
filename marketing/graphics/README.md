# EngCRM marketing graphics

Six graphics, each in the five sizes used for the LearnWohl, LeGuilde and
Notes World banners (`~/ai-workzone/marketing-info-my-apps/<app>/`):

| Size | File suffix | Layout |
| --- | --- | --- |
| 750×300 | `-750x300` | wide banner |
| 640×480 | `-640x480` | 4:3 |
| 750×453 | `-fiverr-750x453` | Fiverr gig image |
| 430×750 | `-430x750` | portrait |
| 300×750 | `-300x750` | narrow portrait |

| Graphic | Message |
| --- | --- |
| `hero` | EngCRM wordmark: finds businesses, researches them, drafts emails; you approve every one |
| `pipeline` | Five agents, one pipeline: Research → Enrich → Scout → Outreach → Follow-up |
| `approval` | Nothing sends without your yes (approval queue) |
| `claude` | Talk to Claude, it runs the pipeline (MCP server) |
| `mobile` | Your CRM in your pocket (log a meeting in one save) |
| `vertical` | One config file, any market |

Style follows the web UI: warm black, champagne gold, Poiret One + Josefin Sans
(self-hosted fonts from `gcrm/ui/static/fonts`).

## Rebuild

```bash
node marketing/graphics/build.mjs            # everything
node marketing/graphics/build.mjs hero claude  # selected graphics
```

Needs Playwright + Chromium. Each graphic/size renders independently; a failure
is reported and the rest still render. Output lands in `out/`.
