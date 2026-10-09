"""Armazenamento histórico de coletas e avaliações preliminares em SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "transparencia.sqlite3"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.environ.get("MPRJ_DB_PATH", DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS entities (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
      uf TEXT NOT NULL, site TEXT, portal TEXT
    );
    CREATE TABLE IF NOT EXISTS evaluations (
      id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL,
      collected_at TEXT NOT NULL, url TEXT,
      http_status INTEGER, error TEXT, page_title TEXT,
      raw_page_json TEXT NOT NULL,
      FOREIGN KEY(entity_id) REFERENCES entities(id)
    );
    CREATE TABLE IF NOT EXISTS criteria_results (
      id INTEGER PRIMARY KEY, evaluation_id INTEGER NOT NULL,
      criterion_id TEXT NOT NULL, status TEXT NOT NULL,
      finding TEXT, evidence_url TEXT, evidence_json TEXT NOT NULL,
      FOREIGN KEY(evaluation_id) REFERENCES evaluations(id)
    );
    CREATE INDEX IF NOT EXISTS ix_evaluations_entity ON evaluations(entity_id, id);
    CREATE INDEX IF NOT EXISTS ix_results_evaluation ON criteria_results(evaluation_id);
    """)
    return conn


def import_collection(source: str | Path, db_path: str | Path | None = None) -> int:
    """Importa JSON real de coletas. A reimportação do mesmo arquivo é idempotente."""
    rows = json.loads(Path(source).read_text(encoding="utf-8"))
    count = 0
    with connect(db_path) as db:
        for item in rows:
            entity, page = item["entity"], item["page"]
            db.execute(
                """INSERT INTO entities(name, uf, site, portal) VALUES(?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET uf=excluded.uf,
                site=excluded.site, portal=excluded.portal""",
                (entity["nome"], entity.get("uf", "RJ"), entity.get("site"), entity.get("portal")),
            )
            entity_id = db.execute(
                "SELECT id FROM entities WHERE name=?", (entity["nome"],)
            ).fetchone()["id"]
            timestamp = page.get("collected_at")
            url = page.get("url")
            existing = db.execute(
                "SELECT id FROM evaluations WHERE entity_id=? AND collected_at=? AND url IS ?",
                (entity_id, timestamp, url)
            ).fetchone()
            if existing:
                continue
            cur = db.execute(
                """INSERT INTO evaluations(
                    entity_id,collected_at,url,http_status,error,page_title,raw_page_json
                ) VALUES (?,?,?,?,?,?,?)""",
                (entity_id, timestamp, url, page.get("http_status"),
                 page.get("error"), page.get("title"), json.dumps(page,ensure_ascii=False))
            )
            for c in item.get("criteria", []):
                db.execute(
                    """INSERT INTO criteria_results(
                        evaluation_id,criterion_id,status,finding,evidence_url,evidence_json
                    ) VALUES (?,?,?,?,?,?)""",
                    (cur.lastrowid, c["criterion_id"], c["status"], c.get("finding"),
                     c.get("evidence_url"), json.dumps(c, ensure_ascii=False))
                )
            count += 1
    return count


def entities(db: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in db.execute("SELECT * FROM entities ORDER BY name")]


def entity(db: sqlite3.Connection, entity_id: int) -> dict | None:
    row = db.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    return dict(row) if row else None


def history(db: sqlite3.Connection, entity_id: int) -> list[dict]:
    return [dict(row) for row in db.execute(
        """SELECT id, entity_id, collected_at, url, http_status, error, page_title
           FROM evaluations WHERE entity_id=? ORDER BY id DESC""", (entity_id,)
    )]


def results(db: sqlite3.Connection, evaluation_id: int) -> list[dict]:
    items = []
    for row in db.execute(
        """SELECT criterion_id,status,finding,evidence_url,evidence_json
           FROM criteria_results WHERE evaluation_id=? ORDER BY criterion_id""",
        (evaluation_id,)
    ):
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json"))
        items.append(item)
    return items


def latest(db: sqlite3.Connection, entity_id: int) -> dict | None:
    runs = history(db, entity_id)
    if not runs:
        return None
    current = runs[0]
    current["criteria"] = results(db, current["id"])
    current["score"] = None  # não há avaliação conclusiva suficiente
    current["score_note"] = "Sem pontuação: coleta exploratória, não auditoria de conformidade"
    return current


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ROOT / "data" / "coletas.json"))
    args = parser.parse_args()
    print(f"Avaliações novas importadas: {import_collection(args.source)}")
