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
    "I help mid-sized and larger companies build custom software and integrate AI into their "
    "workflows — faster and cheaper than a traditional development team because I use AI-augmented "
    "development. Not a ChatGPT wrapper shop: I build real, deployed systems in days to weeks."
)
GOAL = (
    "Find mid-sized and larger companies, research institutions and consulting firms across Bavaria "
    "— Augsburg, Landsberg am Lech, Munich, Nuremberg and the Schwaben region — "
    "that have unmet software, data or process-automation needs. Open a "
    "conversation with a free Digitalisierungs-Check and convert to a €3k–€6k starter project. Funding "
    "programs (Förderung) can cover up to 50% of project costs and should be mentioned in every outreach."
)
WEBSITE = "https://christopherrehm.de"

# What kinds of businesses you're targeting
TARGETS = (
    "Mid-sized and larger companies that make, move, build or grow things: manufacturers with their own "
    "production (own products, contract manufacturing or supplier parts), contract logistics firms, construction companies, food and drink producers, "
    "agricultural businesses, larger trade contractors, clinics and hospitals, and professional "
    "service firms. Also university and research groups, and defence/security consulting firms. "
    "The headquarters of a restaurant or retail chain counts; a single shop, cafe or branch does not."
)

# What makes a contact a strong vs weak fit (used by scout agent for scoring)
FIT_CRITERIA = (
    "Strong fit: a company that produces, transports or builds something itself — its own "
    "production site, warehouse, fleet or construction crews — and runs it on manual steps, "
    "spreadsheets, paper or an ERP it underuses; family-owned firms; companies with "
    "several sites, shift work, quality management (ISO 9001) or heavy document and data flows; "
    "university or research groups needing custom tooling; defence/security consulting firms "
    "needing analysis automation. "
    "Weak fit: shops, cafes, restaurants, petrol stations, car dealers and repair shops, "
    "locksmiths, discount stores and other single-site retail or service outlets; one-person or "
    "family-only businesses; software companies, IT service providers, agencies and tech startups; "
    "Company size is judged separately (see SIZE_RULE). Targets run from regional firms to "
    "international groups with thousands of staff and dozens of sites, so head count, number "
    "of sites or international reach is never a reason for a weak fit. "
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

# Company size, applied by code in the scout (never by the LLM, which misreads thresholds):
# 50 to 5,000 employees, sweet spot 500 to 2,500. Also shown to the research step so its
# notes record what size evidence there is.
SIZE_RULE = (
    "Size: 50 to 5,000 employees, sweet spot 500 to 2,500. Under 50 or over 5,000 is not a fit."
)

# The research step labels every hit with exactly one of these types. Buyer types go on to
# the scout; not-a-buyer types are never saved, and the scout drops any it still finds.
BUYER_TYPES = (
    "manufacturer",
    "trade_contractor",
    "logistics_company",
    "food_producer",
    "construction_company",
    "agricultural_business",
    "clinic_or_hospital",
    "medical_practice",
    "professional_services",
    "research_institution",
    "defence_security",
    "chain_headquarters",
    "other",
)
NOT_A_BUYER_TYPES = (
    "butcher",
    "bakery",
    "supermarket",
    "cafe",
    "restaurant",
    "hotel",
    "gas_station",
    "landmark",
    "car_dealer",
    "car_repair",
    "locksmith",
    "discount_store",
    "retail_shop",
    "gallery",
)

# Scout: positive signals to look for in website/notes content
FIT_SIGNALS = [
    "Familienunternehmen",
    "Produktion / Werk / Fertigung",
    "eigene Produkte",
    "mehrere Standorte / Niederlassungen",
    "Schichtbetrieb",
    "Fuhrpark / Lager",
    "ISO 9001 / Qualitätsmanagement",
    "Karriere page with many open positions",
    "manuelle Prozesse",
    "Excel",
    "ERP (SAP, proALPHA, abas) without visible integration",
    "Lohnfertigung",
    "Zulieferer",
    "Förderung",
    "Forschungsprojekt",
    "Bundeswehr",
    "Verteidigung",
    "Sicherheitsberatung",
]

# Scout: negative signals — contacts matching these are dropped
ANTI_SIGNALS = [
    "Einzelunternehmen / one-person business",
    "single shop, cafe, restaurant or branch outlet",
    "car dealer or repair shop",
    "software company",
    "IT-Dienstleister",
    "Softwarehaus",
    "tech startup",
    "vollständig digitalisiert",
]

# Scan levels — tiered by accessibility and pain intensity (per target-markets analysis).
# Every level aims at companies of 50-5,000 employees; the scout enforces the size.
# Level 1–3: Tier 1 (high pain, reachable decision-makers — start here)
# Level 4–6: Tier 2 (strong pain, slightly harder access)
# Level 7–8: Tier 3 (high value, longer sales cycle)
# Level 9–10: New segments (academia, defence/security consulting)
SCAN_LEVELS: dict[int, dict] = {
    1: {
        "label": "Tier 1 — Larger Trade Contractors (Gebäudetechnik, Anlagenbau)",
        "maps_terms": [
            "Gebäudetechnik",
            "Technische Gebäudeausrüstung",
            "Elektrotechnik GmbH",
            "Haustechnik GmbH",
            "Anlagenbau",
            "Industriemontage",
            "Metallbau GmbH",
            "Fassadenbau",
            "Industrieservice",
        ],
    },
    2: {
        "label": "Tier 1 — Manufacturers & Suppliers (own production)",
        "maps_terms": [
            "Hersteller",
            "Maschinenbau",
            "Sondermaschinenbau",
            "Produktionsunternehmen",
            "Metallverarbeitung",
            "Kunststoffverarbeitung",
            "Elektronikfertigung",
            "Werkzeugbau",
            "Automobilzulieferer",
            "Industriebetrieb",
        ],
    },
    3: {
        "label": "Tier 1 — Contract Logistics & Spedition",
        "maps_terms": [
            "Spedition",
            "Kontraktlogistik",
            "Logistikdienstleister",
            "Logistikzentrum",
            "Lagerlogistik",
            "Internationale Spedition",
            "Güterverkehr",
        ],
    },
    4: {
        "label": "Tier 2 — Food & Beverage Producers",
        "maps_terms": [
            "Brauerei",
            "Molkerei",
            "Käserei",
            "Weingut",
            "Lebensmittelhersteller",
            "Fleischwarenhersteller",
            "Backwarenhersteller",
            "Getränkehersteller",
            "Süßwarenhersteller",
            "Mühle",
        ],
    },
    5: {
        "label": "Tier 2 — Construction Companies (Bauunternehmen)",
        "maps_terms": [
            "Bauunternehmen",
            "Generalunternehmer",
            "Hochbau",
            "Tiefbau",
            "Straßenbau",
            "Ingenieurbau",
            "Fertigbau",
            "Bauträger",
        ],
    },
    6: {
        "label": "Tier 2 — Agricultural Business & Landtechnik",
        "maps_terms": [
            "Landtechnik Hersteller",
            "Landmaschinenhandel",
            "Agrarhandel",
            "Raiffeisen Genossenschaft",
            "Futtermittelhersteller",
            "Saatgut",
            "Maschinenring",
        ],
    },
    7: {
        "label": "Tier 3 — Clinics, Hospitals & MVZ",
        "maps_terms": [
            "Klinikum",
            "Krankenhaus",
            "Fachklinik",
            "Rehaklinik",
            "Medizinisches Versorgungszentrum",
            "Medizinisches Labor",
            "Pflegeeinrichtung",
        ],
    },
    8: {
        "label": "Tier 3 — Professional Services & Company Headquarters",
        "maps_terms": [
            "Steuerberater",
            "Rechtsanwalt",
            "Ingenieurbüro",
            "Ingenieurgesellschaft",
            "Planungsbüro",
            "Architekturbüro",
            "Wirtschaftsprüfer",
            "Unternehmensberatung",
            "Notariat",
            "Firmenzentrale",
            "Hauptverwaltung",
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
