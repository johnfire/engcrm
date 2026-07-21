"""
Unit tests for user-account auth. No DB or HTTP — authenticate() is pure,
and hashing is exercised directly.
"""
from gcrm.api import auth
from gcrm.api.security import hash_password, verify_password


def make_user(password, *, is_active=True, role="admin", user_id=1, email="a@b.com"):
    return {
        "id": user_id,
        "email": email,
        "role": role,
        "is_active": is_active,
        "password_hash": hash_password(password),
    }


class TestPasswordHashing:
    def test_roundtrip(self):
        h = hash_password("s3cret!")
        assert h != "s3cret!"
        assert verify_password("s3cret!", h)

    def test_wrong_password(self):
        assert not verify_password("nope", hash_password("s3cret!"))

    def test_malformed_hash_is_false_not_error(self):
        assert verify_password("x", "not-a-bcrypt-hash") is False


class TestAuthenticate:
    def test_valid_user(self):
        payload = auth.authenticate("a@b.com", "pw", make_user("pw"))
        assert payload == {
            "role": "admin", "user_id": 1, "email": "a@b.com", "token_version": 0,
            "workspace_id": None, "ui_language": "en",
        }

    def test_wrong_password(self):
        assert auth.authenticate("a@b.com", "WRONG", make_user("pw")) is None

    def test_inactive_user_blocked(self):
        assert auth.authenticate("a@b.com", "pw", make_user("pw", is_active=False)) is None

    def test_unknown_user(self):
        assert auth.authenticate("a@b.com", "pw", None) is None

    def test_spectator_role_preserved(self):
        payload = auth.authenticate("a@b.com", "pw", make_user("pw", role="spectator"))
        assert payload["role"] == "spectator"

    def test_break_glass_env_admin(self, monkeypatch):
        monkeypatch.setattr(auth, "ADMIN_PASSWORD", "break-glass-pw")
        payload = auth.authenticate("anyone@x.com", "break-glass-pw", None)
        assert payload["role"] == "admin"
        assert payload["user_id"] is None

    def test_break_glass_disabled_when_unset(self, monkeypatch):
        monkeypatch.setattr(auth, "ADMIN_PASSWORD", "")
        assert auth.authenticate("a@b.com", "anything", None) is None

    def test_real_user_beats_break_glass(self, monkeypatch):
        # A valid user login is honoured even while the break-glass password is set.
        monkeypatch.setattr(auth, "ADMIN_PASSWORD", "break-glass-pw")
        payload = auth.authenticate("a@b.com", "pw", make_user("pw", role="spectator"))
        assert payload["role"] == "spectator"
        assert payload["user_id"] == 1
