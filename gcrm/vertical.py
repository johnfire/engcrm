# gcrm/vertical.py
# ─────────────────────────────────────────────────────────────────────────────
# SWAP THIS FILE TO CHANGE THE VERTICAL.
# Everything else in the system reads from here.
# Run `python setup.py` to regenerate this file interactively.
# ─────────────────────────────────────────────────────────────────────────────

# Who you are and what you're selling
IDENTITY = (
    "Christopher Rehm, freelance AI engineer and consultant based in Klosterlechfeld, Bavaria. "
    "20+ years of hardware and software engineering experience (Intel, full-stack web development). "
    "I help small and medium-sized businesses build custom software and integrate AI into their "
    "workflows — faster and cheaper than a traditional development team because I use AI-augmented "
    "development. Not a ChatGPT wrapper shop: I build real, deployed systems in days to weeks."
)
GOAL = (
    "Find SMBs, professional practices, research institutions, and consulting firms across Bavaria "
    "— Augsburg, Landsberg am Lech, Munich, Nuremberg and the Schwaben region — that have unmet "
    "software or process-automation needs. Open a conversation with a free Digitalisierungs-Check "
    "and convert to a €3k–€6k starter project. Funding programs (Förderung) can cover up to 50% "
    "of project costs and should be mentioned in every outreach."
)
WEBSITE = "https://christopherrehm.de"

# What kinds of businesses you're targeting
TARGETS = (
    "Small and medium-sized businesses in any non-software industry that have operational "
    "inefficiencies, manual workflows, or niche data problems that standard SaaS does not solve. "
    "Target size: too small to hire a dev team, too complex to use off-the-shelf tools. "
    "Also: university professors and research groups needing custom research tools or AI assistants; "
    "consulting firms — including defence and security sector — needing bespoke analysis or "
    "automation tools. Under 1,000 employees preferred; decision-maker must be reachable."
)

# What makes a contact a strong vs weak fit (used by scout agent for scoring)
FIT_CRITERIA = (
    "Strong fit: owner-operated or family businesses running critical workflows on spreadsheets, "
    "paper, or disconnected legacy tools; businesses paying for ERP (SAP, etc.) they dramatically "
    "underutilise; industries with repetitive data-heavy work; businesses where a €3k–€6k project "
    "saves more than it costs within 6 months. "
    "Also strong: university professors or research groups with data processing or custom tooling "
    "needs; defence/security consulting firms needing analysis automation or custom dashboards. "
    "Weak fit: businesses that already use modern, well-integrated software and appear digitised; "
    "large enterprises (1000+ employees) with internal IT departments; software companies, agencies, "
    "or tech startups; businesses where regulatory barriers are prohibitive (e.g. solo medical "
    "practices with no practice manager — not worth the compliance overhead). "
    "Geography: Schwaben primary (within driving distance of Klosterlechfeld), "
    "Munich/Ingolstadt/Nuremberg secondary, rest of Germany remote."
)

# Tone and style for outreach emails
OUTREACH_STYLE = (
    "Direct and professional, written as one businessperson to another. "
    "No buzzwords — never open with 'AI' or 'digital transformation'. "
    "Open with the specific pain point for their industry. "
    "Mention Förderung (funding programs) — up to 50% cost reduction is a strong hook. "
    "Offer a free 30-minute Digitalisierungs-Check as the call to action. "
    "Keep it short: one paragraph on who I am, one sentence on why I'm contacting them "
    "specifically, one clear ask. Feel like a local expert, not a remote agency."
)

# Default language for outreach ("de", "en", "fr", etc.)
LANGUAGE_DEFAULT = "de"

# Scout: contact types that get LLM scoring. All other types are auto-promoted to cold.
SCORED_TYPES: set[str] = {
    "Handwerksbetrieb",
    "Arztpraxis",
    "Einzelhandel",
    "Forschungseinrichtung",
    "Unternehmensberatung",
}

# Scout: positive signals to look for in website/notes content
FIT_SIGNALS = [
    "Inhaber",
    "Familienunternehmen",
    "owner-operated",
    "manuelle Prozesse",
    "Digitalisierung",
    "Excel",
    "no software mentioned on website",
    "contact form as only digital presence",
    "industry-specific niche workflow visible",
    "Lohnfertigung",
    "Zulieferer",
    "Meister",
    "Förderung",
    "Forschungsprojekt",
    "Bundeswehr",
    "Verteidigung",
    "Rüstung",
    "Sicherheitsberatung",
]

# Scout: negative signals — contacts matching these are dropped
ANTI_SIGNALS = [
    "software company",
    "IT-Dienstleister",
    "Softwarehaus",
    "tech startup",
    "1000+ Mitarbeiter",
    "SAP Gold Partner",
    "Salesforce",
    "vollständig digitalisiert",
    "eigene IT-Abteilung",
    "Konzern",
]

# Scan levels — tiered by accessibility and pain intensity (per target-markets analysis).
# Level 1–3: Tier 1 (high pain, reachable decision-makers — start here)
# Level 4–6: Tier 2 (strong pain, slightly harder access)
# Level 7–8: Tier 3 (high value, longer sales cycle)
# Level 9–10: New segments (academia, defence/security consulting)
SCAN_LEVELS: dict[int, dict] = {
    1: {
        "label": "Tier 1 — Handwerk / Skilled Trades (sharpest entry point)",
        "maps_terms": [
            "Handwerksbetrieb",
            "Elektrobetrieb",
            "Elektroinstallateur",
            "Heizung Sanitär",
            "SHK Betrieb",
            "Dachdeckerei",
            "Schreinerei",
            "Malerbetrieb",
            "Zimmerei",
            "Metallbauer",
            "Kfz Werkstatt",
        ],
    },
    2: {
        "label": "Tier 1 — Small Manufacturers & Automotive Suppliers",
        "maps_terms": [
            "Maschinenbau",
            "Metallverarbeitung",
            "Drehtechnik",
            "Frästechnik",
            "Kunststofftechnik",
            "Lohnfertigung",
            "Zulieferer",
            "Werkzeugbau",
            "Elektronikfertigung",
            "Blechverarbeitung",
        ],
    },
    3: {
        "label": "Tier 1 — Logistics, Transport & Spedition",
        "maps_terms": [
            "Spedition",
            "Logistikunternehmen",
            "Transportunternehmen",
            "Kurierdienst",
            "Lagerlogistik",
            "Fuhrpark",
            "Frachtführer",
            "Güterverkehr",
        ],
    },
    4: {
        "label": "Tier 2 — Food & Beverage Producers",
        "maps_terms": [
            "Metzgerei",
            "Fleischerei",
            "Bäckerei",
            "Brauerei",
            "Käserei",
            "Feinkost",
            "Lebensmittelproduktion",
            "Getränkehandel",
            "Weingut",
        ],
    },
    5: {
        "label": "Tier 2 — Construction & Bauunternehmen",
        "maps_terms": [
            "Bauunternehmen",
            "Generalunternehmer",
            "Trockenbau",
            "Tiefbau",
            "Bauträger",
            "Hochbau",
            "Rohbau",
            "Baustelleneinrichtung",
        ],
    },
    6: {
        "label": "Tier 2 — Agricultural Services & Landmaschinen",
        "maps_terms": [
            "Lohnunternehmer",
            "Landmaschinenhandel",
            "Landmaschinenwerkstatt",
            "Agrargenossenschaft",
            "Maschinenring",
            "Agrarbetrieb",
            "Landwirtschaftlicher Betrieb",
        ],
    },
    7: {
        "label": "Tier 3 — Medical Practices & MVZ",
        "maps_terms": [
            "Arztpraxis",
            "Facharztpraxis",
            "Zahnarztpraxis",
            "Physiotherapie",
            "Medizinisches Versorgungszentrum",
            "Ergotherapie",
            "Praxisgemeinschaft",
        ],
    },
    8: {
        "label": "Tier 3 — Professional Services (Steuerberater, Anwälte, Ingenieure)",
        "maps_terms": [
            "Steuerberater",
            "Rechtsanwalt",
            "Ingenieurbüro",
            "Architekturbüro",
            "Wirtschaftsprüfer",
            "Unternehmensberatung",
            "Notariat",
        ],
    },
    9: {
        "label": "Academia — Universities, Fachhochschulen & Research Groups",
        "maps_terms": [
            "Hochschule",
            "Universität",
            "Fachhochschule",
            "Technische Hochschule",
            "Forschungsinstitut",
            "Fraunhofer Institut",
            "DLR",
            "Max-Planck-Institut",
            "Forschungszentrum",
        ],
    },
    10: {
        "label": "Defence, Security & Strategic Consulting Firms",
        "maps_terms": [
            "Sicherheitsberatung",
            "Verteidigungsberatung",
            "Rüstungsunternehmen",
            "Rüstungszulieferer",
            "Bundeswehr Dienstleister",
            "Sicherheitstechnik",
            "Defence Consulting",
            "Strategieberatung",
            "Technologieberatung Verteidigung",
        ],
    },
}

# Interview agent — post-visit debrief configuration
INTERVIEW_APP_NAME = "EngCRM"
INTERVIEW_MATERIALS_OPTIONS = [
    "business card",
    "one-pager",
    "demo link",
    "proposal",
    "case study",
    "Förderung info sheet",
    "nothing",
]
