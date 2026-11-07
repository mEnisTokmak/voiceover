"""SQLite veri katmanı: denetimler, bulgular, düzeltmeler (öğrenme verisi), dersler."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS denetimler (
  id TEXT PRIMARY KEY, uygulama TEXT, platform TEXT, tur TEXT, durum TEXT,
  olusturma TEXT, video_yolu TEXT, senaryo TEXT, drive_link TEXT, log TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bulgular (
  id INTEGER PRIMARY KEY AUTOINCREMENT, denetim_id TEXT, veri TEXT,
  durum TEXT DEFAULT 'beklemede', klip_yolu TEXT, gorsel_yolu TEXT
);
CREATE TABLE IF NOT EXISTS duzeltmeler (
  id INTEGER PRIMARY KEY AUTOINCREMENT, denetim_id TEXT, bulgu_id INTEGER,
  tip TEXT, once TEXT, sonra TEXT, aciklama TEXT, uygulama TEXT, platform TEXT, olusturma TEXT
);
CREATE TABLE IF NOT EXISTS dersler (
  id INTEGER PRIMARY KEY AUTOINCREMENT, metin TEXT, hata_turu TEXT,
  aktif INTEGER DEFAULT 1, kaynak TEXT, olusturma TEXT
);
"""


def _db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA_DIR / "auditor.db", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        con = _db()
        try:
            rows = [dict(r) for r in con.execute(sql, args).fetchall()]
            con.commit()
            return rows
        finally:
            con.close()


def ex(sql: str, args: tuple = ()) -> int:
    with _lock:
        con = _db()
        try:
            cur = con.execute(sql, args)
            con.commit()
            return cur.lastrowid
        finally:
            con.close()


# ---- denetimler
def create_audit(uygulama: str, platform: str, tur: str, video_yolu: str = "", senaryo: str = "") -> str:
    aid = f"{datetime.now():%Y%m%d-%H%M%S}_{uygulama}_{platform}"
    ex("INSERT INTO denetimler (id,uygulama,platform,tur,durum,olusturma,video_yolu,senaryo) VALUES (?,?,?,?,?,?,?,?)",
       (aid, uygulama, platform, tur, "kuyrukta", now(), video_yolu, senaryo))
    return aid


def get_audit(aid: str) -> dict | None:
    r = q("SELECT * FROM denetimler WHERE id=?", (aid,))
    return r[0] if r else None


def list_audits() -> list[dict]:
    return q("SELECT d.*, (SELECT COUNT(*) FROM bulgular b WHERE b.denetim_id=d.id) AS bulgu_sayisi "
             "FROM denetimler d ORDER BY olusturma DESC")


def set_audit(aid: str, **fields) -> None:
    for k, v in fields.items():
        ex(f"UPDATE denetimler SET {k}=? WHERE id=?", (v, aid))


def log(aid: str, msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}\n"
    print(f"{aid}: {msg}", flush=True)
    ex("UPDATE denetimler SET log = COALESCE(log,'') || ? WHERE id=?", (line, aid))


# ---- bulgular
def add_finding(aid: str, veri: dict, klip: str = "", gorsel: str = "", durum: str = "beklemede") -> int:
    return ex("INSERT INTO bulgular (denetim_id,veri,durum,klip_yolu,gorsel_yolu) VALUES (?,?,?,?,?)",
              (aid, json.dumps(veri, ensure_ascii=False), durum, klip, gorsel))


def findings(aid: str) -> list[dict]:
    rows = q("SELECT * FROM bulgular WHERE denetim_id=? ORDER BY id", (aid,))
    for r in rows:
        r["veri"] = json.loads(r["veri"])
    return rows


def get_finding(fid: int) -> dict | None:
    r = q("SELECT * FROM bulgular WHERE id=?", (fid,))
    if not r:
        return None
    r[0]["veri"] = json.loads(r[0]["veri"])
    return r[0]


def update_finding(fid: int, veri: dict | None = None, durum: str | None = None, klip: str | None = None) -> None:
    if veri is not None:
        ex("UPDATE bulgular SET veri=? WHERE id=?", (json.dumps(veri, ensure_ascii=False), fid))
    if durum is not None:
        ex("UPDATE bulgular SET durum=? WHERE id=?", (durum, fid))
    if klip is not None:
        ex("UPDATE bulgular SET klip_yolu=? WHERE id=?", (klip, fid))


def clear_findings(aid: str) -> None:
    ex("DELETE FROM bulgular WHERE denetim_id=? AND durum='beklemede'", (aid,))


def session_path(aid: str) -> Path:
    from .config import sessions_dir
    p = sessions_dir() / aid
    p.mkdir(parents=True, exist_ok=True)
    return p
