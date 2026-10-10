"""Every organization and person records how it was created."""
import ast
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from gcrm import sources
from gcrm.tools import db_organizations, db_people

ROOT = pathlib.Path(__file__).parent.parent
LABELLED = [*sources.KNOWN_SOURCES, "directory_import", "unknown"]


def test_blank_source_is_refused():
    for blank in ("", "   ", None):
        with pytest.raises(ValueError):
            sources.require_source(blank)


def test_labels_recognise_known_directory_and_unexpected_values():
    assert sources.label_key("card_capture") == "card_capture"
    assert sources.label_key("bavaria_directory_2026-08-19") == "directory_import"
    assert sources.label_key(None) == "unknown"
    assert sources.label_key("something_new") == "unknown"


@pytest.mark.parametrize("path", ["gcrm/i18n/en.json", "gcrm/i18n/de.json",
                                  "engcrm-mobile/i18n/en.json", "engcrm-mobile/i18n/de.json"])
def test_every_source_has_a_label_on_web_and_mobile(path):
    keys = json.loads((ROOT / path).read_text())
    assert [name for name in LABELLED if f"source.{name}" not in keys] == []


def test_organization_save_refuses_a_missing_source_before_touching_the_database():
    with patch("gcrm.tools.db_organizations.db") as database:
        with pytest.raises(ValueError):
            db_organizations.save_organization("Acme", "Augsburg", source="")
        with pytest.raises(TypeError):
            db_organizations.save_organization("Acme", "Augsburg")  # type: ignore[call-arg]
    database.assert_not_called()


def test_person_save_refuses_a_missing_source_before_touching_the_database():
    with patch("gcrm.tools.db_people.db") as database:
        with pytest.raises(ValueError):
            db_people.save_person("Anna", source=" ")
        with pytest.raises(TypeError):
            db_people.save_person("Anna")  # type: ignore[call-arg]
    database.assert_not_called()


def test_organization_insert_stores_the_source():
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value = cursor
    cursor.fetchone.side_effect = [None, {"id": 5}]
    with patch("gcrm.tools.db_organizations.db") as database, \
         patch("gcrm.tools.db_organizations._load_ignored_chains", return_value=[]), \
         patch("gcrm.tools.db_organizations.geocode", return_value=None), \
         patch("gcrm.tools.db_organizations.ensure_consent_log"), \
         patch("gcrm.tools.db_organizations.log_audit"):
        database.return_value.__enter__.return_value = connection
        assert db_organizations.save_organization("Acme", "Augsburg", source=sources.VOICE) == 5
    [(sql, params)] = [c.args for c in cursor.execute.call_args_list if "INSERT INTO contacts" in c.args[0]]
    assert "source" in sql
    assert sources.VOICE in params


def test_person_insert_stores_the_source():
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value = cursor
    cursor.fetchone.side_effect = [None, {"id": 8}]
    with patch("gcrm.tools.db_people.db") as database:
        database.return_value.__enter__.return_value = connection
        db_people.save_person("Anna", source=sources.MANUAL_WEB)
    _, params = cursor.execute.call_args_list[-1].args
    assert sources.MANUAL_WEB in params


def _unsourced_creation_calls():
    found = []
    for path in [*(ROOT / "gcrm").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]:
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in {"save_organization", "save_person"} and not any(k.arg == "source" for k in node.keywords):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return found


def test_no_code_path_creates_a_record_without_naming_its_source():
    assert _unsourced_creation_calls() == []


def test_research_agent_saves_are_tagged():
    from gcrm.supervisor import graph
    saver = MagicMock()
    with patch.object(graph, "save_organization", saver), patch.object(graph, "create_research_agent") as create:
        graph._build_research_agent(MagicMock())
    created = create.call_args.kwargs["save_organization"]
    created(name="Acme", city="Augsburg")
    saver.assert_called_once_with(name="Acme", city="Augsburg", source=sources.RESEARCH_AGENT)
