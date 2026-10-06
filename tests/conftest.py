"""Shared test setup: a throwaway database, offline mode, no background watcher."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LLM_MODE"] = "offline"
os.environ["DISABLE_WATCHER"] = "1"
os.environ["DEMO_PASSWORD"] = "TestPass!2026"

import db  # noqa: E402

PASSWORD = "TestPass!2026"


@pytest.fixture()
def fresh_db():
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    db.set_db_path(path)
    db.init_db()
    db.seed(PASSWORD)
    yield path
    db.close()
