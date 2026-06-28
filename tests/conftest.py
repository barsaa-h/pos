import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="function")
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture(autouse=True)
def app(db_path):
    import database as _db_mod
    _db_mod._db_connection = None
    _db_mod.DB_PATH = db_path

    os.environ["FLASK_ENV"] = "testing"
    os.environ["POS_DB_PATH"] = db_path

    # Reset rate limit store per test
    from app import _rate_limit_store
    _rate_limit_store.clear()

    from app import create_app
    from database import init_db

    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        init_db()

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from database import get_db
    with app.app_context():
        with get_db() as conn:
            yield conn


@pytest.fixture
def csrf_token(app, client):
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"
    return "test-csrf-token"


@pytest.fixture
def authed_client(client, csrf_token):
    import time
    with client.session_transaction() as sess:
        sess["admin"] = True
        sess["admin_login_time"] = time.time()
    return client
