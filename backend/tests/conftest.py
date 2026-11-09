"""API tests run against a real PostgreSQL test database.

Set TEST_DATABASE_URL (default: postgresql://localhost:5432/
sports_bet_advisor_test). Tests needing the DB are skipped if it is
unreachable.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

TEST_DB = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://localhost:5432/sports_bet_advisor_test",
)


def _db_available():
    try:
        engine = create_engine(TEST_DB)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except OperationalError:
        return False


@pytest.fixture()
def app(tmp_path):
    if not _db_available():
        pytest.skip(f"PostgreSQL test database not reachable: {TEST_DB}")
    from app import create_app
    from app.extensions import db

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": TEST_DB,
        "JWT_SECRET_KEY": "test-secret-key-at-least-32-bytes-long",
        "MODEL_DIR": tmp_path,
        "ODDS_API_KEY": "",
        "ENABLE_SCHEDULER": False,
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    resp = client.post("/api/auth/register", json={
        "email": "tester@example.com",
        "password": "correct horse",
        "bankroll": 1000,
    })
    assert resp.status_code == 201, resp.json
    token = resp.json["access_token"]
    return {"Authorization": f"Bearer {token}"}
