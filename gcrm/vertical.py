# gcrm/vertical.py
# ─────────────────────────────────────────────────────────────────────────────
# SWAP THIS FILE TO CHANGE THE VERTICAL.
# Everything else in the system reads from here.
# Run `python setup.py` to generate this file interactively.
# ─────────────────────────────────────────────────────────────────────────────

# Who you are and what you're selling
IDENTITY = "Christopher Rehm, watercolor and oil painter based in Klosterlechfeld, Bavaria"
GOAL = (
    "Find venues across Germany and Bavaria that display and sell original artwork, "
    "build relationships with them, and secure exhibition or sales opportunities."
)
WEBSITE = "https://artbychristopherrehm.com"

# What kinds of businesses you're targeting
TARGETS = (
    "galleries, hotel lobbies, restaurants, corporate offices, cafes, "
    "cultural centres, museums, coworking spaces"
)

# What makes a contact a strong vs weak fit (used by scout agent for scoring)
FIT_CRITERIA = (
    "Strong fit: galleries showing regional, emerging, or mid-career artists; "
    "venues that sell work on consignment or display art for atmosphere (hotels, restaurants, offices, cafes); "
    "interior designers who source original art for clients; "
    "coworking spaces and concept stores with a design-conscious aesthetic. "
    "Weak fit: galleries that exclusively represent internationally established or blue-chip artists; "
    "venues with no visible interest in art or decor; "
    "purely commercial or chain businesses with no cultural angle. "
    "Style: contemporary or traditional both welcome, regional landscapes and figurative work a strong fit."
)

# Tone and style for outreach emails
OUTREACH_STYLE = (
    "personal, artist-direct, warm but professional. "
    "Not commercial or templated — each message should feel handwritten."
)

# Default language for outreach ("de", "en", "fr", etc.)
LANGUAGE_DEFAULT = "de"

# Scout: contact types that get LLM scoring. All other types are auto-promoted to cold.
SCORED_TYPES: set[str] = {"gallery"}

# Scout: positive signals to look for in website/notes content
FIT_SIGNALS = [
    "shows emerging or regional artists",
    "rotating exhibitions",
    "open submissions or artist residencies",
    "consignment sales",
    "zeitgenössisch, regional, Nachwuchs, junge Kunst",
]

# Scout: negative signals — contacts matching these are dropped
ANTI_SIGNALS = [
    "exclusively internationally established or blue-chip artists",
    "auction house style",
    "established masters only",
]

# Scan levels — what to search for at each depth.
# Each level has a label and a list of Google Maps search terms.
# Add or remove levels freely; the research agent and UI read from here.
SCAN_LEVELS: dict[int, dict] = {
    1: {
        "label": "Galleries, Cafes, Interior Designers, Coworking",
        "maps_terms": [
            "Kunstgalerie",
            "Galerie",
            "Café",
            "Kaffeehaus",
            "Innenarchitekt",
            "Raumausstatter",
            "Coworking Space",
        ],
    },
    2: {
        "label": "Gift Shops, Esoteric, Concept Stores",
        "maps_terms": [
            "Geschenkeladen",
            "Esoterikladen",
            "Kristallladen",
            "Yoga Studio",
            "Concept Store",
            "Designladen",
            "Boutique",
        ],
    },
    3: {
        "label": "Independent Restaurants",
        "maps_terms": [
            "Restaurant",
            "Gasthaus",
            "Bistro",
            "Weinrestaurant",
            "Gasthof",
        ],
    },
    4: {
        "label": "Corporate Offices & Headquarters",
        "maps_terms": [
            "Firmensitz",
            "Hauptverwaltung",
            "Bürogebäude",
            "Unternehmensberatung",
            "Technologieunternehmen",
        ],
    },
    5: {
        "label": "Hotels",
        "maps_terms": [
            "Hotel",
            "Boutique Hotel",
            "Design Hotel",
            "Landhotel",
            "Stadthotel",
        ],
    },
}
