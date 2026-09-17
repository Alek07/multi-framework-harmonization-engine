from fastapi.testclient import TestClient

from app.catalog.loader import get_catalog


def test_health_check(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    # Liveness plus the loaded catalog version, so the UI can name the running
    # catalog with an empty ledger (BaselinesPage "Catálogo").
    assert response.json() == {"status": "ok", "catalog_version": get_catalog().catalog_version}
