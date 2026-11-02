"""Tests use isolated schemas when BOOKLY_TEST_DATABASE_URL is set; never reset public data."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from bookly.app import create_app
from bookly.db import make_engine


@pytest.fixture
def app(tmp_path):
    url = os.getenv("BOOKLY_TEST_DATABASE_URL")
    admin = None
    schema = None
    if url:
        admin = create_engine(url)
        schema = "bookly_test_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = make_engine(url).execution_options(schema_translate_map={None: schema})
    else:
        engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    application = create_app(model="scripted", engine=engine)
    yield application
    engine.dispose()
    if admin:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        response = client.post("/api/demo/session", json={"customer_id": "maya"})
        assert response.status_code == 200
        yield client


@pytest.fixture
def case(client):
    return client.post("/api/cases", json={"channel": "chat"}).json()


def send(client, case, message, request_id=None):
    response = client.post(
        f"/api/cases/{case['id']}/messages",
        json={
            "text": message,
            "request_id": request_id or uuid4().hex,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()
