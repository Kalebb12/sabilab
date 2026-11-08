"""Tests for the reviewer dashboard (/review)."""

import pytest
from fastapi.testclient import TestClient
import config


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Point every test at a fresh database and set a known review password."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "REVIEW_PASSWORD", "secret")
    from db import init_db
    init_db()
    import importlib, main
    importlib.reload(main)


def _client():
    # Import after monkeypatching
    from main import app
    return TestClient(app, raise_server_exceptions=True)


def test_review_page_wrong_password_shows_login():
    """Wrong password returns the login form, not results."""
    r = _client().get("/review?pw=wrong")
    assert r.status_code == 200
    assert "Reviewer password" in r.text
    assert "Session" not in r.text   # table header absent


def test_review_page_no_password_shows_login():
    """No password shows the login form."""
    r = _client().get("/review")
    assert r.status_code == 200
    assert "Reviewer password" in r.text


def test_review_page_correct_password_shows_table():
    """Correct password renders the results table (even if empty)."""
    r = _client().get("/review?pw=secret")
    assert r.status_code == 200
    assert "No results to review" in r.text or "Session" in r.text


def test_review_login_redirects():
    """POST /review/login redirects to /review with pw query param."""
    r = _client().post("/review/login", data={"password": "secret"}, follow_redirects=False)
    assert r.status_code == 303
    assert "pw=secret" in r.headers["location"]


def test_review_confirm_wrong_password_forbidden():
    """POST /review/confirm with wrong password returns 403."""
    r = _client().post(
        "/review/confirm",
        data={"pw": "bad", "score_id": "1", "session_id": "x", "level": "Foundation", "action": "confirm"},
    )
    assert r.status_code == 403
