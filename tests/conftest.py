import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from idea.database import Database
from idea.repository import Repository

@pytest.fixture
def repo(tmp_path):
    db = Database(tmp_path / "ideas.db", automatic_backup=False)
    yield Repository(db)
    db.close()
