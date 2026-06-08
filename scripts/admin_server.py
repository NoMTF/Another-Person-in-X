#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install dependencies first: python3 -m pip install fastapi uvicorn pydantic") from exc


DEFAULT_FEATURES = {
    "auto_post": True,
    "auto_reply": True,
    "browse_timeline": True,
    "like": True,
    "repost": True,
    "quote": True,
    "follow": True,
    "shadow_mode": False,
    "read_only": False,
    "pause_all": False,
}

DEFAULT_LIMITS = {
    "daily_posts": 5,
    "reply_delay_min_seconds": 45,
    "reply_delay_max_seconds": 600,
    "browse_interval_min_minutes": 20,
    "likes_per_day": 60,
    "reposts_per_day": 12,
    "quotes_per_day": 8,
    "follows_per_day": 8,
    "max_replies_per_hour": 12,
}

RATE_COUNTERS = {
    "post": "daily_posts",
    "reply": "max_replies_per_hour",
    "like": "likes_per_day",
    "repost": "reposts_per_day",
    "quote": "quotes_per_day",
    "follow": "follows_per_day",
}

STATE_DIR = Path(os.environ.get("FACTORY_STATE_DIR", ".")).resolve()
DB_PATH = STATE_DIR / "factory.sqlite3"
ADMIN_TOKEN = os.environ.get("FACTORY_ADMIN_TOKEN", "")


class FeaturePatch(BaseModel):
    key: str
    enabled: bool


class LimitPatch(BaseModel):
    key: str
    value: Union[int, float, str, bool]


class PersonaIn(BaseModel):
    slug: str
    name: str
    path: str
    enabled: bool = True
    version: str = "1"
    notes: str = ""
    traffic_weight: float = 1.0
    rollout_group: str = "stable"


class AuditIn(BaseModel):
    action: str
    actor: str = ""
    target: str = ""
    reason: str = ""
    risk: str = "unknown"
    persona_slug: str = ""
    anchors: List[str] = Field(default_factory=list)
    text: str = ""
    sent: bool = False
    shadow: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryIn(BaseModel):
    category: str
    content: str
    source: str = ""
    confidence: float = 0.5
    persona_slug: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryDigestIn(BaseModel):
    query: str = ""
    persona_slug: str = ""
    limit: int = 12
    max_chars: int = 1800


class OwnerIn(BaseModel):
    kind: str
    value: str
    enabled: bool = True


class RateCheckIn(BaseModel):
    action: str
    actor: str = ""
    increment: bool = False
    window: str = "auto"


class PendingIn(BaseModel):
    action: str
    target: str = ""
    text: str = ""
    reason: str = ""
    persona_slug: str = ""
    risk: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


def connect(path: Path = None) -> sqlite3.Connection:
    if path is None:
        path = DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS personas (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                version TEXT NOT NULL DEFAULT '1',
                notes TEXT NOT NULL DEFAULT '',
                traffic_weight REAL NOT NULL DEFAULT 1.0,
                rollout_group TEXT NOT NULL DEFAULT 'stable',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owners (
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (kind, value)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                target TEXT NOT NULL,
                reason TEXT NOT NULL,
                risk TEXT NOT NULL,
                persona_slug TEXT NOT NULL,
                anchors_json TEXT NOT NULL,
                text TEXT NOT NULL,
                sent INTEGER NOT NULL,
                shadow INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                category TEXT NOT NULL,
                persona_slug TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, category, persona_slug, content='memory', content_rowid='id');
            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
                INSERT INTO memory_fts(rowid, content, category, persona_slug) VALUES (new.id, new.content, new.category, new.persona_slug);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, content, category, persona_slug) VALUES('delete', old.id, old.content, old.category, old.persona_slug);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, content, category, persona_slug) VALUES('delete', old.id, old.content, old.category, old.persona_slug);
                INSERT INTO memory_fts(rowid, content, category, persona_slug) VALUES (new.id, new.content, new.category, new.persona_slug);
            END;
            CREATE TABLE IF NOT EXISTS rate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                text TEXT NOT NULL,
                reason TEXT NOT NULL,
                risk TEXT NOT NULL,
                persona_slug TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )
        for ddl in (
            "ALTER TABLE personas ADD COLUMN traffic_weight REAL NOT NULL DEFAULT 1.0",
            "ALTER TABLE personas ADD COLUMN rollout_group TEXT NOT NULL DEFAULT 'stable'",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass
        now = int(time.time())
        for key, value in {**DEFAULT_FEATURES, **DEFAULT_LIMITS}.items():
            conn.execute(
                "INSERT OR IGNORE INTO config(key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), now),
            )


def require_admin(authorization: str = Header(default="")) -> None:
    if not ADMIN_TOKEN:
        return
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid admin token")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def read_config(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    data = {row["key"]: json.loads(row["value"]) for row in rows}
    for key, value in {**DEFAULT_FEATURES, **DEFAULT_LIMITS}.items():
        data.setdefault(key, value)
    return data


def set_config(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO config(key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, json.dumps(value), int(time.time())),
    )


def memory_rows_to_digest(rows: List[sqlite3.Row], max_chars: int) -> Dict[str, Any]:
    lines = []
    used = 0
    for row in rows:
        content = str(row["content"]).strip()
        if not content:
            continue
        prefix = f"- [{row['category']}"
        if row["persona_slug"]:
            prefix += f"/{row['persona_slug']}"
        prefix += f" c={row['confidence']:.2f}] "
        line = prefix + content.replace("\n", " ")
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return {
        "digest": "\n".join(lines),
        "count": len(lines),
        "max_chars": max_chars,
        "truncated": len(lines) < len(rows),
    }


def window_seconds(action: str, explicit: str = "auto") -> int:
    if explicit == "hour":
        return 3600
    if explicit == "day":
        return 86400
    if explicit == "minute":
        return 60
    if action == "reply":
        return 3600
    return 86400


def make_app() -> FastAPI:
    init_db()
    app = FastAPI(title="OpenClaw Agent Factory Admin", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "state_dir": str(STATE_DIR), "profile": os.environ.get("FACTORY_PROFILE", "")}

    @app.get("/api/config", dependencies=[Depends(require_admin)])
    def get_config() -> Dict[str, Any]:
        with db() as conn:
            data = read_config(conn)
        return {"features": {k: data[k] for k in DEFAULT_FEATURES}, "limits": {k: data[k] for k in DEFAULT_LIMITS}}

    @app.post("/api/config/feature", dependencies=[Depends(require_admin)])
    def update_feature(patch: FeaturePatch) -> Dict[str, Any]:
        if patch.key not in DEFAULT_FEATURES:
            raise HTTPException(status_code=404, detail="unknown feature")
        with db() as conn:
            set_config(conn, patch.key, patch.enabled)
        return {"ok": True}

    @app.post("/api/config/limit", dependencies=[Depends(require_admin)])
    def update_limit(patch: LimitPatch) -> Dict[str, Any]:
        if patch.key not in DEFAULT_LIMITS:
            raise HTTPException(status_code=404, detail="unknown limit")
        with db() as conn:
            set_config(conn, patch.key, patch.value)
        return {"ok": True}

    @app.get("/api/personas", dependencies=[Depends(require_admin)])
    def list_personas() -> List[Dict[str, Any]]:
        with db() as conn:
            rows = conn.execute("SELECT * FROM personas ORDER BY enabled DESC, updated_at DESC").fetchall()
        return [row_to_dict(row) for row in rows]

    @app.post("/api/personas", dependencies=[Depends(require_admin)])
    def upsert_persona(persona: PersonaIn) -> Dict[str, Any]:
        now = int(time.time())
        with db() as conn:
            conn.execute(
                """
                INSERT INTO personas(slug, name, path, enabled, version, notes, traffic_weight, rollout_group, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name=excluded.name,
                    path=excluded.path,
                    enabled=excluded.enabled,
                    version=excluded.version,
                    notes=excluded.notes,
                    traffic_weight=excluded.traffic_weight,
                    rollout_group=excluded.rollout_group,
                    updated_at=excluded.updated_at
                """,
                (
                    persona.slug,
                    persona.name,
                    persona.path,
                    int(persona.enabled),
                    persona.version,
                    persona.notes,
                    persona.traffic_weight,
                    persona.rollout_group,
                    now,
                    now,
                ),
            )
        return {"ok": True}

    @app.get("/api/owners", dependencies=[Depends(require_admin)])
    def list_owners() -> List[Dict[str, Any]]:
        with db() as conn:
            rows = conn.execute("SELECT * FROM owners ORDER BY kind, value").fetchall()
        return [row_to_dict(row) for row in rows]

    @app.post("/api/owners", dependencies=[Depends(require_admin)])
    def upsert_owner(owner: OwnerIn) -> Dict[str, Any]:
        with db() as conn:
            conn.execute(
                "INSERT INTO owners(kind, value, enabled, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(kind, value) DO UPDATE SET enabled=excluded.enabled",
                (owner.kind, owner.value, int(owner.enabled), int(time.time())),
            )
        return {"ok": True}

    @app.get("/api/owners/check", dependencies=[Depends(require_admin)])
    def check_owner(kind: str, value: str) -> Dict[str, Any]:
        with db() as conn:
            row = conn.execute("SELECT enabled FROM owners WHERE kind=? AND value=?", (kind, value)).fetchone()
        return {"owner": bool(row and row["enabled"])}

    @app.post("/api/audit")
    async def add_audit(item: AuditIn, request: Request) -> Dict[str, Any]:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO audit(ts, action, actor, target, reason, risk, persona_slug, anchors_json, text, sent, shadow, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    item.action,
                    item.actor,
                    item.target,
                    item.reason,
                    item.risk,
                    item.persona_slug,
                    json.dumps(item.anchors, ensure_ascii=False),
                    item.text,
                    int(item.sent),
                    int(item.shadow),
                    json.dumps({**item.metadata, "client": request.client.host if request.client else ""}, ensure_ascii=False),
                ),
            )
        return {"ok": True}

    @app.get("/api/audit", dependencies=[Depends(require_admin)])
    def list_audit(limit: int = 100) -> List[Dict[str, Any]]:
        limit = min(max(limit, 1), 500)
        with db() as conn:
            rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = row_to_dict(row)
            item["anchors"] = json.loads(item.pop("anchors_json"))
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    @app.post("/api/memory", dependencies=[Depends(require_admin)])
    def add_memory(item: MemoryIn) -> Dict[str, Any]:
        if not item.content.strip():
            raise HTTPException(status_code=400, detail="empty memory")
        with db() as conn:
            conn.execute(
                "INSERT INTO memory(ts, category, persona_slug, content, source, confidence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(time.time()),
                    item.category,
                    item.persona_slug,
                    item.content,
                    item.source,
                    item.confidence,
                    json.dumps(item.metadata, ensure_ascii=False),
                ),
            )
        return {"ok": True}

    @app.get("/api/memory/search", dependencies=[Depends(require_admin)])
    def search_memory(q: str, limit: int = 20) -> List[Dict[str, Any]]:
        limit = min(max(limit, 1), 100)
        with db() as conn:
            rows = conn.execute(
                """
                SELECT memory.* FROM memory_fts
                JOIN memory ON memory.id = memory_fts.rowid
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts)
                LIMIT ?
                """,
                (q, limit),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    @app.post("/api/memory/digest", dependencies=[Depends(require_admin)])
    def memory_digest(item: MemoryDigestIn) -> Dict[str, Any]:
        limit = min(max(item.limit, 1), 100)
        max_chars = min(max(item.max_chars, 200), 8000)
        with db() as conn:
            if item.query.strip():
                rows = conn.execute(
                    """
                    SELECT memory.* FROM memory_fts
                    JOIN memory ON memory.id = memory_fts.rowid
                    WHERE memory_fts MATCH ?
                      AND (? = '' OR memory.persona_slug = ?)
                    ORDER BY bm25(memory_fts)
                    LIMIT ?
                    """,
                    (item.query, item.persona_slug, item.persona_slug, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM memory
                    WHERE (? = '' OR persona_slug = ?)
                    ORDER BY confidence DESC, ts DESC
                    LIMIT ?
                    """,
                    (item.persona_slug, item.persona_slug, limit),
                ).fetchall()
        digest = memory_rows_to_digest(rows, max_chars)
        digest.update({"query": item.query, "persona_slug": item.persona_slug})
        return digest

    @app.post("/api/rate/check")
    def rate_check(item: RateCheckIn) -> Dict[str, Any]:
        with db() as conn:
            cfg = read_config(conn)
            if cfg.get("pause_all"):
                return {"ok": False, "reason": "pause_all"}
            if cfg.get("read_only") and item.action in RATE_COUNTERS:
                return {"ok": False, "reason": "read_only"}
            limit_key = RATE_COUNTERS.get(item.action)
            if not limit_key:
                return {"ok": True, "reason": "unlimited_action"}
            limit = int(cfg.get(limit_key, DEFAULT_LIMITS[limit_key]))
            since = int(time.time()) - window_seconds(item.action, item.window)
            count = conn.execute("SELECT COUNT(*) AS n FROM rate_events WHERE action=? AND ts>=?", (item.action, since)).fetchone()["n"]
            ok = count < limit
            if ok and item.increment:
                conn.execute("INSERT INTO rate_events(ts, action, actor) VALUES (?, ?, ?)", (int(time.time()), item.action, item.actor))
            return {"ok": ok, "limit": limit, "used": count + (1 if ok and item.increment else 0), "reason": "ok" if ok else "rate_limited"}

    @app.post("/api/pending")
    def add_pending(item: PendingIn) -> Dict[str, Any]:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO pending_actions(ts, status, action, target, text, reason, risk, persona_slug, metadata_json, updated_at)
                VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    item.action,
                    item.target,
                    item.text,
                    item.reason,
                    item.risk,
                    item.persona_slug,
                    json.dumps(item.metadata, ensure_ascii=False),
                    int(time.time()),
                ),
            )
        return {"ok": True}

    @app.get("/api/pending", dependencies=[Depends(require_admin)])
    def list_pending(status: str = "pending", limit: int = 100) -> List[Dict[str, Any]]:
        limit = min(max(limit, 1), 500)
        with db() as conn:
            rows = conn.execute("SELECT * FROM pending_actions WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
        result = []
        for row in rows:
            item = row_to_dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    @app.post("/api/pending/{pending_id}/cancel", dependencies=[Depends(require_admin)])
    def cancel_pending(pending_id: int) -> Dict[str, Any]:
        with db() as conn:
            conn.execute("UPDATE pending_actions SET status='cancelled', updated_at=? WHERE id=? AND status='pending'", (int(time.time()), pending_id))
        return {"ok": True}

    @app.post("/api/pending/cancel-all", dependencies=[Depends(require_admin)])
    def cancel_all_pending() -> Dict[str, Any]:
        with db() as conn:
            cur = conn.execute("UPDATE pending_actions SET status='cancelled', updated_at=? WHERE status='pending'", (int(time.time()),))
        return {"ok": True, "cancelled": cur.rowcount}

    static_dir = Path(__file__).resolve().parents[1] / "assets" / "web-admin" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web-admin")

    return app


app = make_app() if __name__ != "__main__" else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18880)
    parser.add_argument("--state-dir", default=os.environ.get("FACTORY_STATE_DIR", "."))
    args = parser.parse_args()
    global STATE_DIR, DB_PATH
    STATE_DIR = Path(args.state_dir).resolve()
    DB_PATH = STATE_DIR / "factory.sqlite3"
    import uvicorn

    uvicorn.run(make_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
