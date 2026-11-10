"""Tests for database-backed pipeline execution locking."""

from db import init_db
from app.pipeline.telemetry import set_pipeline_status, try_start_pipeline


def test_pipeline_claim_is_exclusive_until_status_changes(tmp_path, monkeypatch):
    db_file = tmp_path / "pipeline_lock.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    init_db(db_file)

    assert try_start_pipeline("session-1") is True
    assert try_start_pipeline("session-1") is False

    set_pipeline_status("session-1", "done")
    assert try_start_pipeline("session-1") is True