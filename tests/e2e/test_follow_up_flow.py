"""An authenticated user reviews and works through independent follow-ups."""
import re

import pytest
from fastapi.testclient import TestClient

from gcrm.api.main import app
from gcrm.api.security import hash_password
from gcrm.tools.db_interactions import log_meeting_note
from gcrm.tools.db_organizations import save_organization
from gcrm.tools.db_users import create_user
from gcrm.tools.follow_up_queries import find_follow_ups

pytestmark = pytest.mark.e2e


def test_review_create_edit_and_complete_with_real_login(clean_database, monkeypatch):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    password = "follow-up-testing-password"
    create_user("followups@example.test", hash_password(password), "admin")
    organization = save_organization("Example GmbH", "Augsburg", source="test_fixture")
    log_meeting_note(organization, "phone", "Spoke", follow_up_text="Send quote")
    client = TestClient(app)
    assert client.post("/login", data={"email": "followups@example.test", "password": password},
                       follow_redirects=False).status_code == 303
    review = client.get("/follow-ups/?view=review&lang=en")
    assert review.status_code == 200
    assert "Send quote" in review.text and "Review older follow-ups" not in review.text
    task = find_follow_ups(status="review")[0]
    response = client.post(f"/follow-ups/{task['id']}/review", data={"decision": "keep",
        "version": task["updated_at"].isoformat(), "task_type": "commitment", "task_text": "Send quote"},
        follow_redirects=False)
    assert response.status_code == 303
    response = client.post("/follow-ups/new", data={"target": f"organization:{organization}",
        "task_type": "check_in", "task_text": "Call back"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/follow-ups/?lang=en")
    assert page.status_code == 200
    assert "Send quote" in page.text and "Call back" in page.text
    assert re.search(r'<button[^>]*value="completed"', page.text)
    first = find_follow_ups()[0]
    response = client.post(f"/follow-ups/{first['id']}/status", data={"status": "completed",
        "version": first["updated_at"].isoformat()}, follow_redirects=False)
    assert response.status_code == 303
    assert len(find_follow_ups()) == 1
