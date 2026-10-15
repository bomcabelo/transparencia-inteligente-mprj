"""Persistência histórica das avaliações (SQLite na POC; esquema portável para PostgreSQL).

Modelo:
  entities ─< assessments ─< results ─< evidences
                   │  └──< pages (HTML original em data/snapshots, endereçado por SHA-256)
  runs ─< assessments            criteria (catálogo versionado)

- toda execução gera um NOVO assessment (histórico imutável); nada é sobrescrito;
- snapshots são endereçados por conteúdo: página que não mudou entre execuções não
  ocupa espaço novo, e o hash prova o que o robô viu;
- reprocessamento (nova versão de regra) cria assessment `reprocessamento` apontando
  para a coleta original, sem acessar o portal de novo.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
from pathlib import Path

from src import database as legacy
from src.collector import Collection
from src.page import Page, parse_html
from src.rules.base import Result

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = Path(os.environ.get("MPRJ_SNAPSHOT_DIR", ROOT / "data" / "snapshots"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS criteria (
  id TEXT NOT NULL, checklist_version TEXT NOT NULL, grupo_id TEXT, grupo TEXT, secao TEXT, matriz TEXT,
  descricao TEXT NOT NULL, fundamentacao TEXT, classificacao TEXT, aplicavel_a TEXT,
  implementado INTEGER NOT NULL DEFAULT 0, complexidade TEXT, tecnica TEXT, regra_versao TEXT,
  PRIMARY KEY (id, checklist_version)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, trigger TEXT NOT NULL,
  methodology_version TEXT, checklist_version TEXT, entities_total INTEGER DEFAULT 0,
  entities_ok INTEGER DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS assessments (
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs(id), entity_id INTEGER NOT NULL REFERENCES entities(id),
  kind TEXT NOT NULL DEFAULT 'coleta', source_assessment_id INTEGER REFERENCES assessments(id),
  collected_at TEXT NOT NULL, evaluated_at TEXT NOT NULL, site_url TEXT, portal_url TEXT, portal_source TEXT,
  collection_status TEXT NOT NULL, health_json TEXT, vendors_json TEXT, probes_json TEXT,
  score REAL, score_min REAL, score_max REAL, media_simples REAL, cobertura_avaliacao REAL,
  cobertura_checklist REAL, comparavel INTEGER, classificacao TEXT, score_json TEXT,
  methodology_version TEXT, checklist_version TEXT, llm_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_assess_entity ON assessments(entity_id, collected_at);
CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL REFERENCES assessments(id), url TEXT NOT NULL,
  final_url TEXT, status INTEGER, fetched_at TEXT, sha256 TEXT, title TEXT, depth INTEGER, renderer TEXT,
  error TEXT, themes_json TEXT, snapshot_path TEXT, screenshot_path TEXT
);
CREATE INDEX IF NOT EXISTS ix_pages_assess ON pages(assessment_id);
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL REFERENCES assessments(id),
  criterion_id TEXT NOT NULL, status TEXT NOT NULL, confidence REAL, finding TEXT, method TEXT,
  rule_version TEXT, needs_review INTEGER, ai_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_results_assess ON results(assessment_id, criterion_id);
CREATE TABLE IF NOT EXISTS evidences (
  id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL REFERENCES results(id), kind TEXT, url TEXT,
  title TEXT, snippet TEXT, detail_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_evid_result ON evidences(result_id);
"""
ENTITY_COLUMNS = {"slug": "TEXT", "tipo": "TEXT", "municipio": "TEXT", "entidade": "TEXT", "ativo": "INTEGER"}


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    db = legacy.connect(db_path)  # cria também as tabelas das etapas anteriores
    db.executescript(SCHEMA)
    existing = {r["name"] for r in db.execute("PRAGMA table_info(entities)")}
    for col, kind in ENTITY_COLUMNS.items():
        if col not in existing:
            db.execute(f"ALTER TABLE entities ADD COLUMN {col} {kind}")
    return db


def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# ------------------------------------------------------------------- escrita
def upsert_entity(db: sqlite3.Connection, e: dict) -> int:
    db.execute("""INSERT INTO entities(name, uf, site, portal, slug, tipo, municipio, entidade, ativo)
                  VALUES (?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(name) DO UPDATE SET uf=excluded.uf, site=excluded.site, portal=excluded.portal,
                  slug=excluded.slug, tipo=excluded.tipo, municipio=excluded.municipio,
                  entidade=excluded.entidade, ativo=excluded.ativo""",
               (e["nome"], e.get("uf", "RJ"), e.get("site"), e.get("portal"), e["id"], e.get("tipo"),
                e.get("municipio"), e.get("entidade"), int(e.get("ativo", True))))
    return db.execute("SELECT id FROM entities WHERE name=?", (e["nome"],)).fetchone()["id"]


def sync_catalog(db: sqlite3.Connection, catalog: dict, registry: dict) -> None:
    for c in catalog["criterios"]:
        meta = registry.get(c["id"], {})
        db.execute("""INSERT OR REPLACE INTO criteria VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (c["id"], catalog["versao"], c["grupo_id"], c["grupo"], c["secao"], c["matriz"], c["descricao"],
                    c["fundamentacao"], c["classificacao"], _j(c["aplicavel_a"]), int(bool(meta)),
                    meta.get("complexidade"), meta.get("tecnica"), meta.get("versao")))


def start_run(db: sqlite3.Connection, trigger: str, methodology: str, checklist: str, started_at: str) -> int:
    return db.execute("INSERT INTO runs(started_at, trigger, methodology_version, checklist_version) VALUES (?,?,?,?)",
                      (started_at, trigger, methodology, checklist)).lastrowid


def finish_run(db: sqlite3.Connection, run_id: int, finished_at: str, total: int, ok: int, notes: str = "") -> None:
    db.execute("UPDATE runs SET finished_at=?, entities_total=?, entities_ok=?, notes=? WHERE id=?",
               (finished_at, total, ok, notes, run_id))


def store_snapshot(entity_slug: str, sha256: str, body: bytes) -> str:
    folder = SNAPSHOTS / entity_slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha256}.html.gz"
    if not path.exists():  # endereçamento por conteúdo: página inalterada não é regravada
        path.write_bytes(gzip.compress(body))
    return str(path.relative_to(SNAPSHOTS))


def save_assessment(db: sqlite3.Connection, *, run_id: int | None, entity_id: int, entity_slug: str,
                    collection: Collection, results: list[Result], score: dict, evaluated_at: str,
                    probes: list | None = None, kind: str = "coleta", source_assessment_id: int | None = None,
                    llm_log: list | None = None) -> int:
    health = collection.health
    status = ("falhou" if not (health["site_ok"] or health["portal_ok"]) else
              "parcial" if not collection.sufficient else "ok")
    cur = db.execute(
        """INSERT INTO assessments(run_id, entity_id, kind, source_assessment_id, collected_at, evaluated_at,
           site_url, portal_url, portal_source, collection_status, health_json, vendors_json, probes_json,
           score, score_min, score_max, media_simples, cobertura_avaliacao, cobertura_checklist, comparavel,
           classificacao, score_json, methodology_version, checklist_version, llm_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, entity_id, kind, source_assessment_id, collection.finished_at or collection.started_at,
         evaluated_at, collection.site_url, collection.portal_url, collection.portal_source, status, _j(health),
         _j(collection.vendors), _j(probes or []), score["score"], score["score_intervalo"][0],
         score["score_intervalo"][1], score["media_simples"], score["cobertura_avaliacao"],
         score["cobertura_checklist"], int(score["comparavel"]), score["classificacao"], _j(score),
         score["metodologia"], score["checklist"], _j(llm_log or [])))
    aid = cur.lastrowid
    for p in collection.pages:
        path = p.snapshot_path
        if not path and p.sha256 in collection.raw:
            path = store_snapshot(entity_slug, p.sha256, collection.raw[p.sha256])
        db.execute("""INSERT INTO pages(assessment_id, url, final_url, status, fetched_at, sha256, title, depth,
                      renderer, error, themes_json, snapshot_path, screenshot_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (aid, p.url, p.final_url, p.status, p.fetched_at, p.sha256 or None, p.title, p.depth,
                    p.renderer, p.error, _j(p.themes), path, p.screenshot_path))
    for r in results:
        rid = db.execute("""INSERT INTO results(assessment_id, criterion_id, status, confidence, finding, method,
                            rule_version, needs_review, ai_json) VALUES (?,?,?,?,?,?,?,?,?)""",
                         (aid, r.criterion_id, r.status, r.confidence, r.finding, r.method, r.rule_version,
                          int(r.needs_review), _j(r.ai) if r.ai else None)).lastrowid
        for e in r.evidences:
            db.execute("INSERT INTO evidences(result_id, kind, url, title, snippet, detail_json) VALUES (?,?,?,?,?,?)",
                       (rid, e.kind, e.url, e.title, e.snippet, _j(e.detail)))
    return aid


def load_collection(db: sqlite3.Connection, assessment_id: int) -> Collection:
    """Reconstrói a coleta a partir dos snapshots (para reprocessar sem acessar o portal)."""
    a = db.execute("""SELECT a.*, e.slug FROM assessments a JOIN entities e ON e.id=a.entity_id
                      WHERE a.id=?""", (assessment_id,)).fetchone()
    if a is None:
        raise KeyError(f"assessment {assessment_id} inexistente")
    col = Collection(entity_id=a["slug"], site_url=a["site_url"], portal_url=a["portal_url"],
                     started_at=a["collected_at"], finished_at=a["collected_at"], portal_source=a["portal_source"])
    col.vendors = json.loads(a["vendors_json"] or "{}")
    for row in db.execute("SELECT * FROM pages WHERE assessment_id=? ORDER BY id", (assessment_id,)):
        if row["snapshot_path"] and (SNAPSHOTS / row["snapshot_path"]).exists():
            body = gzip.decompress((SNAPSHOTS / row["snapshot_path"]).read_bytes())
            page = parse_html(url=row["url"], final_url=row["final_url"], status=row["status"],
                              fetched_at=row["fetched_at"], body=body, depth=row["depth"], renderer=row["renderer"])
            page.snapshot_path, page.screenshot_path = row["snapshot_path"], row["screenshot_path"]
            from src.themes import classify_page
            page.themes = classify_page(page)
        else:
            page = Page(url=row["url"], final_url=row["final_url"], status=row["status"],
                        fetched_at=row["fetched_at"], depth=row["depth"], error=row["error"] or "snapshot_ausente")
            if row["status"] != 200 or row["error"]:
                col.errors.append({"url": row["url"], "status": row["status"], "error": row["error"]})
        col.pages.append(page)
    return col


# ------------------------------------------------------------------- leitura
SUMMARY_COLS = """a.id, a.entity_id, a.run_id, a.kind, a.source_assessment_id, a.collected_at, a.evaluated_at,
  a.site_url, a.portal_url, a.portal_source, a.collection_status, a.score, a.score_min, a.score_max,
  a.media_simples, a.cobertura_avaliacao, a.cobertura_checklist, a.comparavel, a.classificacao,
  a.methodology_version, a.checklist_version"""


def entities(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(f"""SELECT e.id, e.name, e.slug, e.tipo, e.municipio, e.entidade, e.uf, e.site, e.portal,
        la.score, la.classificacao, la.collected_at AS ultima_avaliacao, la.cobertura_avaliacao, la.comparavel,
        la.collection_status
        FROM entities e LEFT JOIN assessments la ON la.id = (
            SELECT id FROM assessments WHERE entity_id=e.id ORDER BY collected_at DESC, id DESC LIMIT 1)
        ORDER BY e.name""").fetchall()
    return [dict(r) for r in rows]


def entity(db: sqlite3.Connection, entity_id: int) -> dict | None:
    row = db.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    return dict(row) if row else None


def history(db: sqlite3.Connection, entity_id: int) -> list[dict]:
    rows = db.execute(f"SELECT {SUMMARY_COLS} FROM assessments a WHERE a.entity_id=? "
                      "ORDER BY a.collected_at, a.id", (entity_id,)).fetchall()
    return [dict(r) for r in rows]


def latest_id(db: sqlite3.Connection, entity_id: int) -> int | None:
    row = db.execute("SELECT id FROM assessments WHERE entity_id=? ORDER BY collected_at DESC, id DESC LIMIT 1",
                     (entity_id,)).fetchone()
    return row["id"] if row else None


def assessment(db: sqlite3.Connection, assessment_id: int, with_evidence: bool = True) -> dict | None:
    a = db.execute(f"SELECT {SUMMARY_COLS}, a.health_json, a.vendors_json, a.probes_json, a.score_json, a.llm_json "
                   "FROM assessments a WHERE a.id=?", (assessment_id,)).fetchone()
    if a is None:
        return None
    out = dict(a)
    names = {"health_json": "saude_coleta", "vendors_json": "vendors", "probes_json": "sondas",
             "score_json": "pontuacao", "llm_json": "ia_log"}
    for key, name in names.items():
        out[name] = json.loads(out.pop(key) or "null")
    out["criteria"] = results(db, assessment_id, with_evidence)
    return out


def results(db: sqlite3.Connection, assessment_id: int, with_evidence: bool = True) -> list[dict]:
    a = db.execute("SELECT checklist_version FROM assessments WHERE id=?", (assessment_id,)).fetchone()
    rows = db.execute("""SELECT r.*, c.descricao, c.grupo, c.grupo_id, c.classificacao, c.fundamentacao, c.matriz,
                         c.complexidade FROM results r LEFT JOIN criteria c
                         ON c.id=r.criterion_id AND c.checklist_version=?
                         WHERE r.assessment_id=? ORDER BY r.id""", (a["checklist_version"], assessment_id)).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["ai"] = json.loads(item.pop("ai_json") or "null")
        item["needs_review"] = bool(item["needs_review"])
        if with_evidence:
            item["evidences"] = [{**dict(e), "detail": json.loads(e["detail_json"] or "{}")}
                                 for e in db.execute("SELECT kind, url, title, snippet, detail_json FROM evidences "
                                                     "WHERE result_id=? ORDER BY id", (r["id"],))]
            for e in item["evidences"]:
                e.pop("detail_json", None)
        items.append(item)
    return items


def criterion_history(db: sqlite3.Connection, entity_id: int, criterion_id: str) -> list[dict]:
    rows = db.execute("""SELECT a.id AS assessment_id, a.collected_at, a.kind, r.status, r.confidence, r.finding,
                         r.rule_version FROM results r JOIN assessments a ON a.id=r.assessment_id
                         WHERE a.entity_id=? AND r.criterion_id=? ORDER BY a.collected_at, a.id""",
                      (entity_id, criterion_id)).fetchall()
    return [dict(r) for r in rows]


def diff(db: sqlite3.Connection, before_id: int, after_id: int) -> dict:
    """Responde: o que foi corrigido, o que piorou, o que segue pendente."""
    rank = {"atende": 3, "parcial": 2, "nao_atende": 1}
    def load(aid):
        return {r["criterion_id"]: r["status"] for r in
                db.execute("SELECT criterion_id, status FROM results WHERE assessment_id=?", (aid,))}
    a, b = load(before_id), load(after_id)
    out = {"de": before_id, "para": after_id, "melhoraram": [], "pioraram": [], "pendentes": [],
           "passaram_a_inconclusivo": [], "novos_conclusivos": []}
    for cid in sorted(set(a) | set(b), key=lambda x: tuple(int(p) for p in x.split("."))):
        s0, s1 = a.get(cid), b.get(cid)
        if s0 in rank and s1 in rank:
            if rank[s1] > rank[s0]:
                out["melhoraram"].append({"criterio": cid, "de": s0, "para": s1})
            elif rank[s1] < rank[s0]:
                out["pioraram"].append({"criterio": cid, "de": s0, "para": s1})
            elif s1 != "atende":
                out["pendentes"].append({"criterio": cid, "status": s1})
        elif s0 in rank and s1 == "inconclusivo":
            out["passaram_a_inconclusivo"].append({"criterio": cid, "de": s0})
        elif s1 in rank and s0 not in rank:
            out["novos_conclusivos"].append({"criterio": cid, "para": s1})
            if s1 != "atende":
                out["pendentes"].append({"criterio": cid, "status": s1})
    return out


def first_compliance(db: sqlite3.Connection, entity_id: int) -> dict[str, str]:
    """Data em que cada critério passou a 'atende' pela última vez (sem regressão depois)."""
    since: dict[str, str] = {}
    for r in db.execute("""SELECT r.criterion_id, r.status, a.collected_at FROM results r
                           JOIN assessments a ON a.id=r.assessment_id WHERE a.entity_id=? AND a.kind='coleta'
                           ORDER BY a.collected_at, a.id""", (entity_id,)):
        if r["status"] == "atende":
            since.setdefault(r["criterion_id"], r["collected_at"])
        elif r["status"] in ("parcial", "nao_atende"):
            since.pop(r["criterion_id"], None)
    return since


def runs(db: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]


def criteria(db: sqlite3.Connection, checklist_version: str | None = None) -> list[dict]:
    if checklist_version is None:
        row = db.execute("SELECT checklist_version FROM criteria ORDER BY rowid DESC LIMIT 1").fetchone()
        checklist_version = row["checklist_version"] if row else ""
    rows = db.execute("SELECT * FROM criteria WHERE checklist_version=?", (checklist_version,)).fetchall()
    out = [dict(r) | {"aplicavel_a": json.loads(r["aplicavel_a"] or "[]")} for r in rows]
    return sorted(out, key=lambda c: tuple(int(p) for p in c["id"].split(".")))
