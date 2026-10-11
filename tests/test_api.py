from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["evaluations_executed"] == 0

def test_entities_endpoint():
    r = client.get("/entities")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    for entity in r.json():
        assert {'id', 'name', 'uf'} <= set(entity)

def test_unknown_entity():
    r = client.get("/entities/999")
    assert r.status_code == 404
