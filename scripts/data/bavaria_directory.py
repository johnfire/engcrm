"""
Bavaria startup & innovation ecosystem directory, transcribed for import.

Source of truth for humans stays the markdown briefing
(rehm-consulting/marketing/start-up-techhub/bavaria-startup-ecosystem-directory.md,
compiled 19 August 2026). This module is the machine-readable transcription of
its tables — parsing the markdown was rejected because the document mixes three
different table shapes with prose, so a curated list is both safer to review and
honest about what was actually taken from it.

Conventions:
  * `website` is exactly what the document listed, or "" where it printed "—".
    Nothing is guessed here — missing sites are filled in later by the importer's
    lookup pass, which searches and verifies rather than inventing a domain.
  * A functional address (transfer@, forschung@, info@) belongs to the org, a
    personal one to the `person`. The CRM dedupes contacts on email, so putting
    someone's personal address on their institution would be wrong.
  * `city` is the seat named by the document or carried in the institution's own
    name; additional sites go in the notes rather than inventing extra rows.
  * Section A ("Regional Startup Hubs & Ecosystems") is deliberately NOT imported.
    Its entries are places — Munich, Ingolstadt, Erlangen — not organisations, and
    as CRM rows they were worse than useless: enrichment resolved them to their
    city administrations, putting town-hall addresses into the outreach pipeline.
    The organisations that actually sit in those places are already covered by
    sections B and C below.
"""

SOURCE = "bavaria_directory_2026-08-19"

# Digital Gründerzentren — the state-co-funded network (section B1).
STARTUP_CENTRES = [
    {"name": "Alte Schlosserei", "city": "Aschaffenburg", "website": "dgz-ab.de",
     "notes": "Digitales Gründerzentrum. Digital business models. Also sited in Lohr am Main."},
    {"name": "ANsWERK", "city": "Ansbach", "website": "answerk.de",
     "notes": "Digitales Gründerzentrum."},
    {"name": "Areal Digital", "city": "Leipheim", "website": "",
     "notes": "Digitales Gründerzentrum. No website listed in the source directory."},
    {"name": "brigk", "city": "Ingolstadt", "website": "brigk.digital",
     "notes": "Digitales Gründerzentrum. Automotive/mobility region (Audi HQ)."},
    {"name": "brigkAIR", "city": "Manching", "website": "brigkair.digital",
     "notes": "Digitales Gründerzentrum. Autonomous mobility. Also sited in Ingolstadt."},
    {"name": "DGO (Digitale Gründerinitiative Oberpfalz)", "city": "Regensburg",
     "website": "digitale-oberpfalz.de",
     "notes": "Digitales Gründerzentrum. Also sited in Amberg and Weiden."},
    {"name": "IGZ (digital centres)", "city": "Cham", "website": "igz-cham.de",
     "notes": "Digitales Gründerzentrum. Seminars and specialist forums. Also Roding, Furth im Wald."},
    {"name": "Technology Campus Parsberg-Lupburg", "city": "Parsberg-Lupburg",
     "website": "dgz-par.de", "notes": "Digitales Gründerzentrum."},
    {"name": "DZ.S (Digitales Zentrum Schwaben)", "city": "Augsburg", "website": "schwaben.digital",
     "notes": "Digitales Gründerzentrum, anchor site aiti-Park/aitiRaum (aitiraum.de). "
              "Industrie 4.0, materials, mechatronics. Second site in Kempten."},
    {"name": "Einstein1", "city": "Hof", "website": "einstein1.net",
     "notes": "Digitales Gründerzentrum. Big-data and healthcare focus."},
    {"name": "GZDN (Gründerzentrum Digitalisierung Niederbayern)", "city": "Passau",
     "website": "gzdn.de",
     "notes": "Digitales Gründerzentrum, five coordinated sites: Passau (INN.KUBATOR), Landshut, "
              "Deggendorf (ITC1), Pfarrkirchen, Freyung. University-anchored."},
    {"name": "LAGARDE1", "city": "Bamberg", "website": "lagarde1.de",
     "notes": "Digitales Gründerzentrum. Digital transformation and 3D printing."},
    {"name": "Starthouse Spessart", "city": "Lohr am Main", "website": "lohr.de/starthouse-spessart",
     "notes": "Digitales Gründerzentrum."},
    {"name": "STELLWERK18", "city": "Rosenheim", "website": "stellwerk18.de",
     "notes": "Digitales Gründerzentrum. Campus-style hub, TH Rosenheim."},
    {"name": "WERK1", "city": "München", "website": "werk1.com",
     "notes": "Digitales Gründerzentrum."},
    {"name": "ZDI Mainfranken", "city": "Würzburg", "website": "zdi-mainfranken.de",
     "notes": "Digitales Gründerzentrum. Idea labs and prototyping. Also Schweinfurt, Bad Kissingen."},
    {"name": "ZOLLHOF Tech Incubator", "city": "Nürnberg", "website": "zollhof.de",
     "notes": "Digitales Gründerzentrum. One of Germany's fastest-growing tech incubators; "
              "anchors Digital Hub Health with Medical Valley."},
    {"name": "Zukunft.Coburg.Digital", "city": "Coburg", "website": "zcd.digital",
     "notes": "Digitales Gründerzentrum. Also sited in Rödental."},
    {"name": "TechBase Regensburg", "city": "Regensburg", "website": "techbase.de",
     "notes": "Digitales Gründerzentrum. 25-year-old innovation campus, sensor tech; "
              "near OTH Regensburg and Uni Regensburg."},
]

# Munich sector/corporate incubators and accelerators (section B2).
INCUBATORS = [
    {"name": "UnternehmerTUM", "city": "München", "website": "unternehmertum.de",
     "notes": "Cross-sector; Europe's largest university-based innovation and entrepreneurship centre (TUM)."},
    {"name": "appliedAI", "city": "München", "website": "appliedai.de",
     "notes": "Applied AI adoption for industry. UnternehmerTUM affiliate."},
    {"name": "Xpreneurs", "city": "München", "website": "xpreneurs.io",
     "notes": "Deep-tech market-readiness programme (UnternehmerTUM)."},
    {"name": "TechFounders", "city": "München", "website": "techfounders.com",
     "notes": "Industrial tech: automotive, mobility, robotics, IIoT."},
    {"name": "LMU Entrepreneurship Center (IEC)", "city": "München", "website": "iec.lmu.de",
     "notes": "Academic and student spin-offs (LMU)."},
    {"name": "Strascheg Center for Entrepreneurship (SCE)", "city": "München", "website": "sce.de",
     "notes": "Applied-sciences entrepreneurship (Munich Business School / HM-affiliated)."},
    {"name": "CDTM (Center for Digital Technology and Management)", "city": "München",
     "website": "cdtm.de", "notes": "ICT research and tech entrepreneurship. TUM/LMU joint venture."},
    {"name": "Gate Garching", "city": "Garching", "website": "gate-garching.de",
     "notes": "IT, health, mechatronics, deep-tech. TUM Garching campus."},
    {"name": "ESA Business Incubation Centre (BIC) Bavaria", "city": "München", "website": "esa-bic.de",
     "notes": "Space-tech commercialization."},
    {"name": "IZB (Innovation und Gründerzentrum Biotechnologie)", "city": "Planegg",
     "website": "izb-online.de", "notes": "Medical biotech. Martinsried/Planegg cluster."},
    {"name": "BioM", "city": "Planegg", "website": "bio-m.org",
     "notes": "Biotech cluster management, Munich-Martinsried."},
    {"name": "Media Lab Bayern", "city": "München", "website": "medialab-bayern.de",
     "notes": "Digital journalism and media startups."},
    {"name": "Plug and Play Munich", "city": "München", "website": "plugandplaytechcenter.com/munich",
     "notes": "InsurTech, health, retail-tech. Corporate matchmaking."},
    {"name": "Wayra (Telefónica/O2)", "city": "München", "website": "wayra.com",
     "notes": "Telecom-adjacent tech, corporate-backed."},
    {"name": "German Accelerator", "city": "München", "website": "germanaccelerator.com",
     "notes": "International market-entry support."},
    {"name": "Impact Hub Munich", "city": "München", "website": "munich.impacthub.net",
     "notes": "Social entrepreneurship."},
    {"name": "Munich Urban Colab", "city": "München", "website": "munich-urban-colab.de",
     "notes": "Urban and mobility solutions, city-backed."},
    {"name": "Munich Technology Center (MTZ)", "city": "München", "website": "mtz.de",
     "notes": "General tech-sector startups and coworking."},
    {"name": "Retailtech Hub", "city": "München", "website": "retailhub.tech",
     "notes": "Retail technology, REWE-backed."},
    {"name": "SAP.iO Foundry Munich", "city": "München", "website": "sap.io/munich",
     "notes": "B2B software, SAP ecosystem."},
    {"name": "BMW Startup Garage", "city": "München", "website": "bmwstartupgarage.com",
     "notes": "Automotive tech, corporate."},
    {"name": "ProSiebenSat.1 Accelerator", "city": "München", "website": "",
     "notes": "Media-tech, corporate. No website found: the source directory saw LinkedIn only, and a follow-up search returned conflicting signals (Crunchbase lists the accelerator as permanently closed while other profiles still describe it as running). Confirm it exists before any outreach."},
    {"name": "WFP Innovation Accelerator", "city": "München", "website": "innovation.wfp.org",
     "notes": "Humanitarian/hunger-tech. UN World Food Programme unit based in Munich."},
]

# Statewide funding and matchmaking body (section B3).
FUNDING_NETWORKS = [
    {"name": "BayStartUP", "city": "München", "website": "baystartup.de",
     "notes": "Central startup-financing institution for Bavaria. Runs the Bavarian Business Plan "
              "Competitions (Munich, Northern Bavaria, Swabia, Ideenreich) and curates deal flow for "
              "~EUR 50M+/year in early-stage investment; business-angel/VC and startup-corporate matchmaking.",
     "person": {"name": "Carsten Rudolph", "title": ""}},
]

# University technology-transfer offices (section C1, TBU + TBHAW tiers).
UNIVERSITY_TRANSFER = [
    {"name": "Universität Augsburg", "city": "Augsburg", "website": "uni-augsburg.de",
     "person": {"name": "Roland Grenz", "email": "roland.grenz@uni-a.de"}},
    {"name": "Universität Bamberg", "city": "Bamberg", "website": "uni-bamberg.de/transfer",
     "email": "transfer.fft@uni-bamberg.de", "person": {"name": "Dr. Henriette Neef"}},
    {"name": "Universität Bayreuth", "city": "Bayreuth", "website": "iei.uni-bayreuth.de",
     "person": {"name": "David Eder", "email": "david.eder@uni-bayreuth.de"}},
    {"name": "Katholische Universität Eichstätt-Ingolstadt", "city": "Eichstätt", "website": "ku.de/transfer",
     "person": {"name": "Dr. Daniel Zacher", "email": "daniel.zacher@ku.de"}},
    {"name": "FAU Erlangen-Nürnberg", "city": "Erlangen", "website": "fau.de/outreach",
     "email": "zuv-wtt@fau.de", "person": {"name": "Sybille Barth"}},
    {"name": "LMU München", "city": "München", "website": "lmu.de/forschungstransfer",
     "notes": "Runs its own transfer/licensing function rather than routing through BayPAT.",
     "person": {"name": "Dr. Philipp Baaske", "email": "baaske@vicepresident.lmu.de"}},
    {"name": "TU München", "city": "München", "website": "forte.tum.de",
     "person": {"name": "Elke Achhammer", "email": "achhammer@zv.tum.de"}},
    {"name": "Universität der Bundeswehr München", "city": "München", "website": "unibw.de/entrepreneurship",
     "email": "info@unibw.de"},
    {"name": "TU Nürnberg", "city": "Nürnberg", "website": "", "email": "transfer-service@utn.de",
     "person": {"name": "Dr. Christina Wittmann"}},
    {"name": "Universität Passau", "city": "Passau", "website": "uni-passau.de/transfer",
     "person": {"name": "Dr. Günther Hribek", "email": "guenther.hribek@uni-passau.de"}},
    {"name": "Universität Regensburg", "city": "Regensburg", "website": "uni-regensburg.de/forschung/futur",
     "email": "outreach@ur.de", "person": {"name": "Jutta Gügel"}},
    {"name": "Universität Würzburg (JMU)", "city": "Würzburg", "website": "uni-wuerzburg.de/sft",
     "person": {"name": "Dr. Iris Zwirner-Baier", "email": "iris.zwirner-baier@uni-wuerzburg.de"}},
    {"name": "OTH Amberg-Weiden", "city": "Amberg", "website": "oth-aw.de",
     "person": {"name": "Michael Tschapka", "email": "m.tschapka@oth-aw.de"}},
    {"name": "Hochschule Ansbach", "city": "Ansbach", "website": "hs-ansbach.de/forschung",
     "person": {"name": "Dr. Anne Buhmann", "email": "anne.buhmann@hs-ansbach.de"}},
    {"name": "TH Aschaffenburg", "city": "Aschaffenburg", "website": "th-ab.de/forschung",
     "person": {"name": "Dr. Tilo Gockel", "email": "tilo.gockel@th-ab.de"}},
    {"name": "TH Augsburg", "city": "Augsburg", "website": "tha.de/itw", "email": "itw@tha.de",
     "person": {"name": "Gabriele Schwarz"}},
    {"name": "Hochschule Coburg", "city": "Coburg", "website": "",
     "person": {"name": "Dr. Markus Neufeld", "email": "markus.neufeld@hs-coburg.de"}},
    {"name": "TH Deggendorf", "city": "Deggendorf", "website": "",
     "person": {"name": "Christian Schopf", "email": "christian.schopf@th-deg.de"}},
    {"name": "Hochschule Hof", "city": "Hof", "website": "hof-university.de",
     "person": {"name": "Claus Beyerlein", "email": "claus.beyerlein@hof-university.de"}},
    {"name": "TH Ingolstadt (THI)", "city": "Ingolstadt", "website": "thi.de/forschung",
     "person": {"name": "Anja Zupfer", "email": "anja.zupfer@thi.de"}},
    {"name": "Hochschule Kempten", "city": "Kempten", "website": "hs-kempten.de/forschung",
     "email": "transfer@hs-kempten.de"},
    {"name": "Hochschule Landshut", "city": "Landshut", "website": "",
     "person": {"name": "Dr. Hedwig Maurer", "email": "hedwig.maurer@haw-landshut.de"}},
    {"name": "Hochschule München (HM)", "city": "München", "website": "hm.edu",
     "email": "forschung@hm.edu", "person": {"name": "Dr. Jürgen Meier"}},
    {"name": "Katholische Stiftungshochschule München", "city": "München", "website": "ksh-muenchen.de",
     "person": {"name": "Prof. Dr. Christoph Ellßel", "email": "christoph.ellssel@ksh-m.de"}},
    {"name": "Hochschule Neu-Ulm", "city": "Neu-Ulm", "website": "hnu.de",
     "person": {"name": "Michael Junger", "email": "michael.junger@hnu.de"}},
    {"name": "TH Nürnberg (Georg Simon Ohm)", "city": "Nürnberg", "website": "th-nuernberg.de",
     "person": {"name": "Sandra Knakrügge", "email": "sandra.knakruegge@th-nuernberg.de"}},
    {"name": "Evangelische Hochschule Nürnberg", "city": "Nürnberg", "website": "evhn.de/forschung",
     "person": {"name": "Vanessa König", "email": "vanessa.koenig@evhn.de"}},
    {"name": "OTH Regensburg", "city": "Regensburg", "website": "oth-regensburg.de/forschen",
     "person": {"name": "Dr. Marcus Graf", "email": "marcus.graf@oth-regensburg.de"}},
    {"name": "TH Rosenheim", "city": "Rosenheim", "website": "th-rosenheim.de",
     "person": {"name": "Wolfgang Alversammer", "email": "wolfgang.alversammer@th-rosenheim.de"}},
    {"name": "Hochschule Weihenstephan-Triesdorf", "city": "Freising", "website": "hswt.de",
     "email": "forschung@hswt.de", "notes": "Agri-food-tech.",
     "person": {"name": "Dr. Michael Krappmann"}},
    {"name": "TH Würzburg-Schweinfurt (THWS)", "city": "Würzburg", "website": "caf.thws.de",
     "person": {"name": "Dr. Christian Lengl", "email": "christian.lengl@thws.de"}},
]

# Art/music university transfer offices (section C1, TBKH tier). The source
# directory listed contacts and emails only — no websites at all.
ART_SCHOOL_TRANSFER = [
    {"name": "Akademie der Bildenden Künste München", "city": "München", "website": "",
     "person": {"name": "Angela Holzwig", "email": "holzwig@adbk.mhn.de"}},
    {"name": "HFF München (Hochschule für Fernsehen und Film)", "city": "München", "website": "",
     "notes": "Film.", "person": {"name": "Simon von der Au", "email": "s.vonderau@hff-muc.de"}},
    {"name": "Hochschule für Musik und Theater München", "city": "München", "website": "",
     "person": {"name": "Prof. Maurice Lausberg", "email": "maurice.lausberg@hmtm.de"}},
    {"name": "Akademie der Bildenden Künste Nürnberg", "city": "Nürnberg", "website": "",
     "person": {"name": "Petra Meyer", "email": "meyer@adbk-nuernberg.de"}},
    {"name": "Hochschule für Musik Nürnberg", "city": "Nürnberg", "website": "",
     "person": {"name": "Prof. Maren Wilhelm", "email": "maren.wilhelm@hfm-nuernberg.de"}},
    {"name": "Hochschule für Musik Würzburg", "city": "Würzburg", "website": "",
     "person": {"name": "Prof. Clara Blessing", "email": "clara.blessing@hfm-wuerzburg.de"}},
]

# Patent/licensing arms and research institutes (sections C2 and C3).
LICENSING_BODIES = [
    {"name": "BayPAT (Bayerische Patentallianz GmbH)", "city": "München", "website": "baypat.de",
     "email": "kontakt@baypat.de", "phone": "+49 89 5480177-0",
     "address": "Prinzregentenstr. 52, 80538 München",
     "notes": "Shared patent/licensing commercialization arm owned by 28 Bavarian universities and "
              "research institutions. Highest-leverage single contact point for licensable Bavarian "
              "university IP. Self-reported: ~3,900 inventions evaluated, 2,600+ patents filed, "
              "~600 commercialized, ~EUR 50M cumulative licensing revenue, 160+ startups supported."},
    {"name": "Max Planck Innovation GmbH", "city": "München", "website": "max-planck-innovation.com",
     "notes": "Technology-transfer and licensing arm for the entire Max Planck Society. Patenting, "
              "licensing and spin-off support for all Max Planck Institutes, including the Bavarian "
              "ones (MPI of Biochemistry, Astrophysics, Quantum Optics, Plasma Physics, Psychiatry)."},
]

RESEARCH_INSTITUTES = [
    {"name": "Fraunhofer IIS", "city": "Erlangen", "website": "",
     "notes": "Fraunhofer Institute for Integrated Circuits — the MP3-codec institute, strong "
              "industry-licensing track record. Only Bavarian Fraunhofer site confirmed by the source "
              "directory; transfer is decentralised per institute, with Fraunhofer Venture supporting "
              "spin-offs group-wide."},
]

# Websites the source document did not carry, found afterwards and confirmed by
# fetching the page and checking it names the organisation. Kept apart from the
# transcription above so it stays a faithful copy of the briefing, and so the
# provenance of every non-document value is visible.
RESEARCHED_WEBSITES = {
    "Fraunhofer IIS": ("iis.fraunhofer.de", "web search; page fetch matched fraunhofer, iis, integrierte"),
    "Akademie der Bildenden Künste München": ("adbk.de", "web search; page fetch matched akademie, bildenden, künste"),
    # No standalone domain — the centre lives on the Landkreis Günzburg site.
    "Areal Digital": ("www.guenzburg-meinlandkreis.de/fuer-unternehmen/areal-digital/",
                      "web search; page fetch returned the Areal Digital page"),
}

# type -> rows. The CRM's `type` column is what makes this import filterable
# apart from the art-marketing pipeline that shares the contacts table.
SECTIONS = {
    "startup_centre": STARTUP_CENTRES,
    "incubator": INCUBATORS,
    "funding_network": FUNDING_NETWORKS,
    "university_transfer": UNIVERSITY_TRANSFER,
    "art_school_transfer": ART_SCHOOL_TRANSFER,
    "patent_licensing": LICENSING_BODIES,
    "research_institute": RESEARCH_INSTITUTES,
}


def all_rows() -> list[tuple[str, dict]]:
    """(type, row) for every organisation, with researched websites merged in.

    A researched value only ever fills a gap — it can never replace a website the
    document itself carried.
    """
    merged = []
    for kind, rows in SECTIONS.items():
        for row in rows:
            found = RESEARCHED_WEBSITES.get(row["name"])
            if found and not row.get("website"):
                row = {**row, "website": found[0]}
            merged.append((kind, row))
    return merged
