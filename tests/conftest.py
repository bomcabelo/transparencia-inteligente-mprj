import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Banco e snapshots isolados por teste (nunca toca data/)."""
    db = tmp_path / "t.sqlite3"
    monkeypatch.setenv("MPRJ_DB_PATH", str(db))
    from src import repository
    monkeypatch.setattr(repository, "SNAPSHOTS", tmp_path / "snapshots")
    return db
