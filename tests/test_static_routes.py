from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_page_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Разделим" in response.text


def test_status_page_served():
    response = client.get("/status")
    assert response.status_code == 200
    assert "Статус сборов" in response.text


def test_organizer_page_served():
    response = client.get("/organizer")
    assert response.status_code == 200
    assert "Создать сбор" in response.text


def test_create_session_without_organizer_ids():
    response = client.post(
        "/sessions",
        json={
            "title": "Сбор для друзей",
            "total_amount": 2000,
            "head_count": 5,
            "requisites": "+79990002233"
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Сбор для друзей"
    assert data["per_head"] == 400.0
