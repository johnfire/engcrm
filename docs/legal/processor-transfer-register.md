# Processor and transfer register — technical draft

This register is a technical evidence pack, not a claim that agreements or
transfer safeguards exist. The controller or counsel must fill the status
columns before enabling or continuing each flow.

| Recipient | Processing/data | Location | Required decision/evidence | Current technical status |
|---|---|---|---|---|
| IONOS | app, database, backups | Germany | Art. 28 hosting agreement; backup location/retention | host configured; agreement not stored here |
| Proton | outreach and inbox email | Switzerland | DPA and service terms | enabled when email is enabled |
| Anthropic | OCR, extraction, drafting and classification prompts | United States | DPA, current DPF/SCC/TIA evidence | supported provider; review required |
| Google Maps/Places | research queries and business-location results | United States | terms, DPA/role, transfer evidence | enabled with Maps key |
| Expo | push token and notification body | United States | DPA, current DPF/SCC/TIA evidence | enabled with mobile notifications |
| Bright Data | target-site URLs and fetched content | Israel | DPA and terms | optional feature |
| DeepSeek | CRM prompts | China | Art. 28 agreement plus Art. 46 mechanism/TIA | administrator-selectable; controller decision required |

## Release gate

Do not introduce a new processor until this register has the relevant executed
DPA, transfer mechanism/TIA where needed, controller approval date, and a
matching update to `/privacy` and the Art. 30 record.
