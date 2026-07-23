from fastapi.testclient import TestClient


def test_create_and_get_user(client: TestClient) -> None:
    payload = {"email": "jane@example.com", "password": "s3cret", "full_name": "Jane Doe"}
    create_response = client.post("/api/v1/users/", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["email"] == payload["email"]
    assert "password" not in created

    get_response = client.get(f"/api/v1/users/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["email"] == payload["email"]


def test_create_duplicate_user_fails(client: TestClient) -> None:
    payload = {"email": "dupe@example.com", "password": "s3cret"}
    client.post("/api/v1/users/", json=payload)
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 409


def test_get_missing_user_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
