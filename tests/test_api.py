from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["evaluations_executed"] == 0

def test_entities_initially_empty():
    r = client.get("/entities")
    assert r.status_code == 200
    assert r.json() == []

def test_unknown_entity():
    r = client.get("/entities/999")
    assert r.status_code == 404
