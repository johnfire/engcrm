"""Upload validation on the mobile card endpoint (content-type gate)."""
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token

client = TestClient(main.app)
ADMIN = {"Authorization": f"Bearer {create_token('admin')}"}


def test_card_rejects_non_image_content_type():
    # A non-image upload is rejected (415) before any DB access.
    r = client.post(
        "/api/cards",
        headers=ADMIN,
        files={"image": ("note.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 415
