import pytest

import app.main as api
from app.metrics import METRICS


@pytest.fixture(autouse=True)
def isolated_app(tmp_path, monkeypatch):
    """Keep tests from writing to the committed support_events.log or leaking state between tests."""
    monkeypatch.setattr(api, "LOG_PATH", tmp_path / "events.log")
    api.STATE.update(incident_mode="normal", rules_version=None)
    METRICS.reset()
    yield
    api.STATE.update(incident_mode="normal", rules_version=None)
