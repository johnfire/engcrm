"""Reading a lead list (the master table of ~/ai-workzone/marketing-leads/HOWTO-city-lead-lists.md)
into businesses and people, without any LLM. Rows are real ones from the Buchloe and Ulm lists."""
import pytest

from gcrm.lead_list import LeadListError, parse_lead_list, row_town, split_address

HEADER = ("| Pg | # | Business | Location | Address | Website | Contact | Role | LinkedIn | LinkedIn status | Notes |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|\n")
VION = ("| 7 | 1 | Vion Beef Süd GmbH (formerly A. Moksel AG) | Nordwest I / III | Rudolf-Diesel-Str. 10, 86807 Buchloe "
        "| vion.com | — | — | — | no contact yet | Slaughterhouse now Vion. |\n")
KARWENDEL_1 = ("| 7 | 2 | Karwendel-Werke Huber GmbH & Co. KG | Nordwest I / III | Karwendelstr. 6-16, 86807 Buchloe "
               "| karwendel.de | Paul Platzhalter | Geschäftsführer (sole, per Lebensmittelzeitung; may be dated) | — "
               "| no profile found | Dairy. |\n")
KARWENDEL_2 = ("| 7 | 3 | Karwendel-Werke Huber GmbH & Co. KG | Nordwest I / III | Karwendelstr. 6-16, 86807 Buchloe "
               "| karwendel.de | Erika Muster | Sprecher der Geschäftsführung (Impressum) "
               "| [profile](https://www.linkedin.com/in/erika-muster-3a71/) | not sent | Same business as the rows above. |\n")
PCG = ("| 12 | 2 | PCG – Public Cloud Group | Science Park II | Lise-Meitner-Str. 3-1, 89081 Ulm | pcg.io "
       "| Kim Beispiel | Geschäftsführer (Impressum) | [candidate](https://www.linkedin.com/in/kim-beispiel/) | not sent "
       "| PCG not named in the headline. |\n")
CONNECTED = ("| 3 | 9 | Beispiel AG | Innovationspark | Am Technologiezentrum 5, 86159 Augsburg | beispiel.de "
             "| Anna Berg | CTO | [profile](https://www.linkedin.com/in/anna-berg/) | connected | |\n")
PAGE_INDEX = "\n## Page index\n\n| Page | Rows |\n|---|---|\n| 7 | 1-3 |\n"


def test_rows_of_one_business_become_one_company_with_its_people():
    businesses = parse_lead_list(HEADER + VION + KARWENDEL_1 + KARWENDEL_2 + PAGE_INDEX)
    assert [business["name"] for business in businesses] == [
        "Vion Beef Süd GmbH (formerly A. Moksel AG)", "Karwendel-Werke Huber GmbH & Co. KG"]
    karwendel = businesses[1]
    assert karwendel["address"] == "Karwendelstr. 6-16, 86807 Buchloe" and karwendel["city"] == "Buchloe"
    assert karwendel["area"] == "Nordwest I / III" and karwendel["website"] == "https://karwendel.de"
    assert [person["name"] for person in karwendel["people"]] == ["Paul Platzhalter", "Erika Muster"]


def test_a_business_without_a_contact_has_no_people():
    (vion,) = parse_lead_list(HEADER + VION)
    assert vion["people"] == [] and "Slaughterhouse now Vion." in vion["notes"]


def test_a_confirmed_profile_is_kept_and_a_candidate_is_not_taken_as_confirmed():
    karwendel, pcg = parse_lead_list(HEADER + KARWENDEL_2 + PCG)
    assert karwendel["people"][0]["linkedin_url"] == "https://www.linkedin.com/in/erika-muster-3a71/"
    assert pcg["people"][0]["linkedin_url"] is None
    assert pcg["people"][0]["linkedin_candidate"] == "https://www.linkedin.com/in/kim-beispiel/"


def test_the_linkedin_status_and_role_are_kept_per_person():
    (business,) = parse_lead_list(HEADER + CONNECTED)
    person = business["people"][0]
    assert (person["role"], person["linkedin_status"], person["connected"]) == ("CTO", "connected", True)


def test_only_the_master_table_is_read():
    areas = "## Areas\n\n| Area | State |\n|---|---|\n| Nordwest I / III | done |\n\n"
    businesses = parse_lead_list(areas + HEADER + VION + PAGE_INDEX)
    assert len(businesses) == 1


def test_a_file_without_the_master_table_is_refused_with_a_reason():
    with pytest.raises(LeadListError, match="Pg \\| # \\| Business"):
        parse_lead_list("# Notes\n\n| Office park | Company |\n|---|---|\n| X | Y |\n")


def test_a_row_with_the_wrong_number_of_cells_is_reported_not_guessed():
    with pytest.raises(LeadListError, match="row 1"):
        parse_lead_list(HEADER + "| 7 | 1 | Only three cells |\n")


@pytest.mark.parametrize("address, expected", [
    ("Rudolf-Diesel-Str. 10, 86807 Buchloe", ("86807", "Buchloe")),
    ("Lise-Meitner-Str. 3-1, 89081 Ulm", ("89081", "Ulm")),
    ("Siemensstraße 21, 86836 Untermeitingen-Lagerlechfeld", ("86836", "Untermeitingen-Lagerlechfeld")),
    ("address unknown", (None, None)),
    ("—", (None, None)),
    ("Werner-von-Siemens-Str. 6, 86159 Augsburg (Geb. 9a)", ("86159", "Augsburg")),
    ("Bergiusstr. 17, 86199 Augsburg (HQ listed: Pilsener Str. 5, 86159)", ("86199", "Augsburg")),
    ("Leopoldstr. 23, 80802 München; Augsburg office Peter-Dörfler-Str. 32", ("80802", "München")),
    ("Hartmähderweg 11, Kaufbeuren", (None, "Kaufbeuren")),
    ("Kaufbeuren", (None, "Kaufbeuren")),
    ("— (possibly Glatz Logistik GmbH, Robert-Bunsen-Str. 7)", (None, None)),
])
def test_postcode_and_town_are_read_from_the_address(address, expected):
    assert split_address(address) == expected


def test_a_pipe_inside_the_notes_stays_part_of_the_notes():
    """Real Buchloe row 113: a copied LinkedIn headline put 'Coach | SECONU' into the notes."""
    row = ("| 15 | 113 | KDVM Seminare & Coaching | INNOVA Allgäu Hightech-Park | Innovapark 20, 87600 Kaufbeuren "
           "| kdvm.com | Otto Test | Founder and CEO (Impressum) | [profile](https://www.linkedin.com/in/otto-test/) "
           "| not sent | headline: Consultant and Coach | SECONU Experts, Kaufbeuren. |\n")
    (business,) = parse_lead_list(HEADER + row)
    assert business["notes"] == "headline: Consultant and Coach | SECONU Experts, Kaufbeuren."
    assert business["people"][0]["linkedin_status"] == "not sent"


def test_an_address_marked_unknown_is_kept_as_a_note_not_as_the_address():
    row = ("| 3 | 4 | Glatz Spedition | Alpina-Ring | — (possibly Glatz Logistik GmbH, Robert-Bunsen-Str. 7) "
           "| — | — | — | — | no contact yet | Not on Maps. |\n")
    (business,) = parse_lead_list(HEADER + row)
    assert business["address"] == ""
    assert "Address: — (possibly Glatz Logistik GmbH, Robert-Bunsen-Str. 7)" in business["notes"]


@pytest.mark.parametrize("business, expected", [
    ({"postcode": "86807", "city": "Buchloe"}, "Buchloe"),
    ({"postcode": None, "city": "Augsburg Süd"}, "Augsburg"),
    ({"postcode": None, "city": "Innovationspark Augsburg"}, "Augsburg"),
    ({"postcode": None, "city": "Augsburg textile quarter"}, "Augsburg"),
    ({"postcode": None, "city": "Kaufbeuren"}, "Kaufbeuren"),
    ({"postcode": None, "city": None}, "Augsburg"),
    ({"postcode": "80802", "city": "München"}, "München"),
    ({"postcode": None, "city": "Augsburger Land"}, "Augsburger Land"),
])
def test_a_town_without_postcode_that_names_the_default_town_is_that_town(business, expected):
    """'TONI Park, Augsburg Süd' is in Augsburg, not in a town called 'Augsburg Süd'."""
    assert row_town(business, "Augsburg") == expected


def test_without_a_default_town_the_row_keeps_its_own_town_or_none():
    assert row_town({"postcode": None, "city": "Augsburg Süd"}, "") == "Augsburg Süd"
    assert row_town({"postcode": None, "city": None}, "") is None
