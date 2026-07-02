import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["POS_DB_PATH"] = path
    from database import init_db
    init_db()
    yield path
    os.unlink(path)


@pytest.fixture
def db(db_path):
    from database import get_db
    with get_db() as conn:
        yield conn
