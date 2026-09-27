import hashlib
import hmac
import json
import os
import time
from unittest.mock import AsyncMock
from typing import Optional
from urllib.parse import urlencode

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/razdelim-hackathon-tests.db")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")

from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app
from app.max_sdk import MaxSDK

TEST_BOT_TOKEN = os.environ["BOT_TOKEN"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def signed_init_data(
    user_id: int,
    first_name: str = "Tester",
    auth_date: Optional[int] = None,
) -> str:
    params = {
        "auth_date": str(auth_date or int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": first_name}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", TEST_BOT_TOKEN.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


def test_root_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Разделим" in response.text


def test_health_endpoint_served(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_status_page_served(client):
    response = client.get("/status")
    assert response.status_code == 200
    assert "Статус сборов" in response.text


def test_organizer_page_served(client):
    response = client.get("/organizer")
    assert response.status_code == 200
    assert "Создать сбор" in response.text


def test_sdk_scripts_are_included_in_pages(client):
    root = client.get("/")
    organizer = client.get("/organizer")
    status = client.get("/status")

    assert root.status_code == 200
    assert '/static/max-sdk.js' in root.text
    assert '/static/max-sdk.js' in organizer.text
    assert '/static/max-sdk.js' in status.text
    assert '/static/max-parent-sdk.js' not in root.text + organizer.text + status.text


def test_organizer_endpoints_require_signed_max_user(client):
    assert client.get("/sessions").status_code == 401
    assert client.get("/sessions/1/status").status_code == 401


def test_expired_max_init_data_is_rejected(client):
    response = client.post(
        "/sessions",
        json={
            "title": "Устаревшая подпись",
            "total_amount": 100,
            "head_count": 2,
            "requisites": "test",
            "init_data": signed_init_data(101, auth_date=int(time.time()) - 86401),
        },
    )
    assert response.status_code == 401


def test_max_auth_fails_closed_without_bot_token(client, monkeypatch):
    monkeypatch.setattr(main_module, "BOT_TOKEN", "")
    response = client.post(
        "/sessions",
        json={
            "title": "Нет токена",
            "total_amount": 100,
            "head_count": 2,
            "requisites": "test",
            "init_data": signed_init_data(101),
        },
    )
    assert response.status_code == 503


def test_webhook_secret_and_chat_recipient(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_WEBHOOK_SECRET", "test-webhook-secret")
    send_message = AsyncMock()
    monkeypatch.setattr(main_module, "send_message", send_message)
    update = {
        "update_type": "bot_started",
        "user": {"user_id": 501},
        "chat_id": 901,
    }

    assert client.post("/webhook/max", json=update).status_code == 401
    response = client.post(
        "/webhook/max",
        json=update,
        headers={"X-Max-Bot-Api-Secret": "test-webhook-secret"},
    )
    assert response.status_code == 200
    send_message.assert_awaited_once()
    assert send_message.await_args.kwargs["chat_id"] == 901
    assert "startapp=organizer" in send_message.await_args.kwargs["text"]


def test_max_sdk_targets_chat_id_without_user_id():
    sdk = MaxSDK()
    request = {}

    async def capture_post(path, **kwargs):
        request["path"] = path
        request.update(kwargs)
        return None

    sdk.post = capture_post
    import asyncio

    asyncio.run(sdk.send_message(chat_id=901, text="Привет"))
    assert request["path"] == "/messages"
    assert request["params"]["chat_id"] == 901
    assert "user_id" not in request["params"]
    assert request["headers"]["Authorization"] == sdk.config.access_token
    assert "access_token" not in request["params"]


def test_session_creation_and_status_are_limited_to_owner(client):
    init_data = signed_init_data(101, "Organizer")
    create_response = client.post(
        "/sessions",
        json={
            "title": "Сбор на поход",
            "total_amount": 1200,
            "head_count": 3,
            "requisites": "+79990002222",
            "init_data": init_data,
        },
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    owner_headers = {"X-Max-Init-Data": init_data}
    assert client.get("/sessions", headers=owner_headers).json()[0]["id"] == session_id
    assert client.get(f"/sessions/{session_id}/status", headers=owner_headers).status_code == 200

    other_headers = {"X-Max-Init-Data": signed_init_data(202, "Other")}
    assert client.get("/sessions", headers=other_headers).json() == []
    assert client.get(f"/sessions/{session_id}/status", headers=other_headers).status_code == 404


def test_list_and_fetch_sessions(client):
    init_data = signed_init_data(303, "Organizer")
    create_response = client.post(
        "/sessions",
        json={
            "title": "Список сессий",
            "total_amount": 1200,
            "head_count": 3,
            "requisites": "+79990002222",
            "init_data": init_data,
        },
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    headers = {"X-Max-Init-Data": init_data}
    list_response = client.get("/sessions", headers=headers)
    assert list_response.status_code == 200
    data = list_response.json()
    assert any(item["id"] == session_id for item in data)

    detail_response = client.get(f"/sessions/{session_id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == session_id


def test_create_session_without_organizer_ids(client):
    response = client.post(
        "/sessions",
        json={
            "title": "Сбор для друзей",
            "total_amount": 2000,
            "head_count": 5,
            "requisites": "+79990002233",
            "init_data": signed_init_data(404, "Organizer"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Сбор для друзей"
    assert data["per_head"] == 400.0
