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


def test_user_flows_reject_requests_without_max_init_data(client):
    create_response = client.post(
        "/sessions",
        json={
            "title": "Без MAX",
            "total_amount": 100,
            "head_count": 2,
            "requisites": "test",
        },
    )
    join_response = client.post("/join", json={"start_param": "test-token"})
    confirm_response = client.post("/confirm", json={"participant_id": 1})

    assert create_response.status_code == 422
    assert join_response.status_code == 422
    assert confirm_response.status_code == 422
    assert client.get("/sessions/1/status").status_code == 401


def test_local_demo_flow_without_max(client, monkeypatch):
    monkeypatch.setattr(main_module, "APP_ENV", "development")
    monkeypatch.setattr(main_module, "DEMO_MODE", True)
    monkeypatch.setattr(main_module, "BOT_TOKEN", "")
    monkeypatch.setattr(main_module, "is_local_demo", lambda request: True)

    with TestClient(app, base_url="http://127.0.0.1") as local_client:
        create_response = local_client.post(
            "/sessions",
            json={
                "title": "Тестовый поход",
                "total_amount": 1200,
                "head_count": 3,
                "requisites": "Тестовые реквизиты",
                "init_data": "DEMO",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert "demo=participant&startapp=" in created["link"]

        start_param = created["link"].split("startapp=", 1)[1]
        join_response = local_client.post(
            "/join",
            json={"init_data": "DEMO", "start_param": start_param},
        )
        assert join_response.status_code == 200
        participant_id = join_response.json()["participant_id"]
        assert join_response.json()["share_amount"] == 400

        confirm_response = local_client.post(
            "/confirm",
            json={"init_data": "DEMO", "participant_id": participant_id},
        )
        assert confirm_response.status_code == 200

        status_response = local_client.get(
            f"/sessions/{created['id']}/status",
            headers={"X-Max-Init-Data": "DEMO"},
        )
        assert status_response.status_code == 200
        assert status_response.json()["paid_count"] == 1


def test_local_demo_is_rejected_for_non_loopback_clients(client, monkeypatch):
    monkeypatch.setattr(main_module, "APP_ENV", "development")
    monkeypatch.setattr(main_module, "DEMO_MODE", True)
    monkeypatch.setattr(main_module, "BOT_TOKEN", "")

    with TestClient(app, base_url="http://example.test") as remote_client:
        response = remote_client.post(
            "/sessions",
            json={
                "title": "Remote demo",
                "total_amount": 100,
                "head_count": 2,
                "requisites": "test",
                "init_data": "DEMO",
            },
        )
    assert response.status_code == 503


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


def test_equal_mode_distributes_cents_and_closes_at_target(client):
    organizer_init = signed_init_data(601, "Organizer")
    create_response = client.post(
        "/sessions",
        json={
            "title": "Поровну с копейками",
            "total_amount": 10.01,
            "head_count": 3,
            "requisites": "test",
            "payment_mode": "equal",
            "init_data": organizer_init,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    start_param = created["link"].rsplit("=", 1)[1]
    shares = []

    for user_id in (611, 612, 613):
        join_response = client.post(
            "/join",
            json={"init_data": signed_init_data(user_id), "start_param": start_param},
        )
        assert join_response.status_code == 200
        participant = join_response.json()
        shares.append(participant["share_amount"])
        confirmation = client.post(
            "/confirm",
            json={
                "init_data": signed_init_data(user_id),
                "participant_id": participant["participant_id"],
            },
        )
        assert confirmation.status_code == 200

    assert shares == [3.34, 3.34, 3.33]
    headers = {"X-Max-Init-Data": organizer_init}
    status_response = client.get(f"/sessions/{created['id']}/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["remaining_amount"] == 0
    assert status_response.json()["paid_count"] == 3

    full_response = client.post(
        "/join",
        json={"init_data": signed_init_data(614), "start_param": start_param},
    )
    assert full_response.status_code == 409


def test_flexible_mode_caps_contributions_and_prevents_double_charge(client):
    organizer_init = signed_init_data(701, "Organizer")
    create_response = client.post(
        "/sessions",
        json={
            "title": "Свободные взносы",
            "total_amount": 100,
            "head_count": 4,
            "requisites": "test",
            "payment_mode": "flexible",
            "init_data": organizer_init,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    start_param = created["link"].rsplit("=", 1)[1]
    user_id = 711
    user_init = signed_init_data(user_id)
    join_response = client.post(
        "/join",
        json={"init_data": user_init, "start_param": start_param},
    )
    assert join_response.status_code == 200
    participant_id = join_response.json()["participant_id"]
    assert join_response.json()["payment_mode"] == "flexible"
    assert join_response.json()["remaining_amount"] == 100

    overpayment = client.post(
        "/confirm",
        json={"init_data": user_init, "participant_id": participant_id, "contribution_amount": 100.01},
    )
    assert overpayment.status_code == 409

    first_payment = client.post(
        "/confirm",
        json={"init_data": user_init, "participant_id": participant_id, "contribution_amount": 35.50},
    )
    assert first_payment.status_code == 200
    duplicate_payment = client.post(
        "/confirm",
        json={"init_data": user_init, "participant_id": participant_id, "contribution_amount": 35.50},
    )
    assert duplicate_payment.status_code == 200
    assert duplicate_payment.json()["already_paid"] is True

    other_user_init = signed_init_data(712)
    other_join = client.post(
        "/join",
        json={"init_data": other_user_init, "start_param": start_param},
    )
    other_payment = client.post(
        "/confirm",
        json={
            "init_data": other_user_init,
            "participant_id": other_join.json()["participant_id"],
            "contribution_amount": 64.50,
        },
    )
    assert other_payment.status_code == 200

    status_response = client.get(
        f"/sessions/{created['id']}/status",
        headers={"X-Max-Init-Data": organizer_init},
    )
    status = status_response.json()
    assert status["remaining_amount"] == 0
    assert status["paid_count"] == 2
    assert sorted(item["contribution_amount"] for item in status["participants"]) == [35.5, 64.5]


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
