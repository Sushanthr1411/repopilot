from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_body():
    response = client.get("/api/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "repopilot-ai"
