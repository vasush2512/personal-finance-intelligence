"""Shared test setup.

Isolates the suite from data/model.joblib. Without this, whether a test
passes depends on whether someone has run a training job on this machine —
tests that expect "the rules found nothing, so it stays 'other'" quietly
start getting model predictions instead. Tests that want a model build one
in a tmp_path and pass its path explicitly.
"""

import pytest

from app.services import importer


@pytest.fixture(autouse=True)
def no_model_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MODEL_PATH", tmp_path / "no-such-model.joblib")
