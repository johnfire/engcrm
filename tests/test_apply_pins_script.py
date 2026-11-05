"""The review printout of scripts/maps/apply_pins.py: pins first, each with the Maps title,
so a wrong match is seen before it is recorded."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("apply_pins", Path(__file__).parent.parent / "scripts/maps/apply_pins.py")
apply_pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_pins)


def test_saved_and_already_pinned_come_first_with_their_maps_title():
    lines = apply_pins.review_lines([
        {"id": 3, "crm": "Carglass", "status": "name_mismatch", "title": "Carglass Augsburg"},
        {"id": 2, "crm": "Meile GmbH", "status": "saved", "title": "Meile GmbH"},
        {"id": 1, "crm": "Beispiel AG", "status": "no_match", "results": ["Beispiel Bau", "Beispiel Haus"]},
        {"id": 4, "crm": "Faist", "status": "already", "title": "FAIST Systeme GmbH"},
    ])
    assert lines[0].startswith("already") and "FAIST Systeme GmbH" in lines[0]
    assert lines[1].startswith("saved") and "#2 Meile GmbH  →  Meile GmbH" in lines[1]
    assert "Beispiel Bau, Beispiel Haus" in lines[3]
