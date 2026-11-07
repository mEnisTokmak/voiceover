"""Öğrenme: denetçinin düzeltmeleri kaydedilir ve sonraki analizlerde istemlere eklenir.

Üç tür geri bildirim:
  duzeltme      -> bulgu yanlış etiketlenmiş/yazılmış, denetçi düzeltti (önce -> sonra)
  eksik         -> sistem kaçırdı, denetçi "ekstra hata" olarak ekledi
  yanlis_pozitif-> sistem hata dedi ama hata değil, denetçi reddetti

Ders (kalıcı kural): denetçinin yazdığı veya düzeltmeden otomatik üretilen kısa cümle.
Model yeniden eğitilmez; geçmiş düzeltmeler ve dersler her analizde talimata eklenir (few-shot).
"""
from __future__ import annotations

import json

from . import store
from .config import settings

KARSILASTIRILAN = ["baslik", "hata_turu", "wcag", "seviye", "not", "cozum_onerisi", "onem", "ekran"]


def _ozet(f: dict | None) -> dict:
    if not f:
        return {}
    keys = KARSILASTIRILAN + ["soylenen", "kontrol_id"]
    return {k: f.get(k) for k in keys if f.get(k) not in (None, "", [])}


def record_correction(audit: dict, finding_id: int, once: dict, sonra: dict, ders: str = "") -> None:
    degisen = [k for k in KARSILASTIRILAN if (once.get(k) or "") != (sonra.get(k) or "")]
    if not degisen and not ders:
        return
    store.ex("INSERT INTO duzeltmeler (denetim_id,bulgu_id,tip,once,sonra,aciklama,uygulama,platform,olusturma) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (audit["id"], finding_id, "duzeltme", json.dumps(_ozet(once), ensure_ascii=False),
              json.dumps(_ozet(sonra), ensure_ascii=False), ders, audit["uygulama"], audit["platform"], store.now()))
    if ders.strip():
        add_lesson(ders.strip(), sonra.get("hata_turu", ""), "denetçi")
    elif "hata_turu" in degisen:
        ipucu = once.get("soylenen") or once.get("baslik", "")
        add_lesson(f"\"{ipucu}\" benzeri durumlar \"{once.get('hata_turu')}\" değil "
                   f"\"{sonra.get('hata_turu')}\" olarak sınıflandırılmalı.", sonra.get("hata_turu", ""), "otomatik")


def record_missed(audit: dict, finding_id: int, finding: dict, ders: str = "") -> None:
    store.ex("INSERT INTO duzeltmeler (denetim_id,bulgu_id,tip,once,sonra,aciklama,uygulama,platform,olusturma) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (audit["id"], finding_id, "eksik", "{}", json.dumps(_ozet(finding), ensure_ascii=False), ders,
              audit["uygulama"], audit["platform"], store.now()))
    if ders.strip():
        add_lesson(ders.strip(), finding.get("hata_turu", ""), "denetçi")


def record_rejected(audit: dict, finding_id: int, finding: dict, neden: str = "") -> None:
    store.ex("INSERT INTO duzeltmeler (denetim_id,bulgu_id,tip,once,sonra,aciklama,uygulama,platform,olusturma) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (audit["id"], finding_id, "yanlis_pozitif", json.dumps(_ozet(finding), ensure_ascii=False), "{}",
              neden, audit["uygulama"], audit["platform"], store.now()))
    if neden.strip():
        add_lesson(f"Hata DEĞİL: {neden.strip()} (örnek: \"{finding.get('baslik', '')}\")",
                   finding.get("hata_turu", ""), "denetçi")


def add_lesson(metin: str, hata_turu: str = "", kaynak: str = "denetçi") -> int:
    return store.ex("INSERT INTO dersler (metin,hata_turu,aktif,kaynak,olusturma) VALUES (?,?,1,?,?)",
                    (metin, hata_turu, kaynak, store.now()))


def lessons(only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM dersler" + (" WHERE aktif=1" if only_active else "") + " ORDER BY id DESC"
    return store.q(sql)


def prompt_context(uygulama: str, platform: str) -> str:
    """Analiz istemine eklenecek öğrenilmiş bilgi bloğu."""
    s = settings().get("ogrenme", {})
    max_ders, max_ornek = s.get("en_fazla_ders", 40), s.get("en_fazla_ornek", 10)
    parts: list[str] = []

    ders = lessons(only_active=True)[:max_ders]
    if ders:
        parts.append("### Öğrenilmiş kurallar (denetçi tarafından)\n" +
                     "\n".join(f"- [{d['hata_turu'] or 'genel'}] {d['metin']}" for d in ders))

    # Aynı uygulama + platform önce, sonra diğerleri
    rows = store.q("SELECT * FROM duzeltmeler ORDER BY (uygulama=? AND platform=?) DESC, id DESC LIMIT ?",
                   (uygulama, platform, max_ornek))
    if rows:
        lines = []
        for r in rows:
            once, sonra = json.loads(r["once"] or "{}"), json.loads(r["sonra"] or "{}")
            if r["tip"] == "duzeltme":
                lines.append(f"- DÜZELTME ({r['uygulama']}/{r['platform']}): sistem şunu üretti {json.dumps(once, ensure_ascii=False)}"
                             f" → denetçi şöyle düzeltti {json.dumps(sonra, ensure_ascii=False)}"
                             + (f" — açıklama: {r['aciklama']}" if r["aciklama"] else ""))
            elif r["tip"] == "eksik":
                lines.append(f"- KAÇIRILAN ({r['uygulama']}/{r['platform']}): sistem bulamadı, denetçi ekledi "
                             f"{json.dumps(sonra, ensure_ascii=False)}. Benzer durumları ara.")
            else:
                lines.append(f"- YANLIŞ POZİTİF ({r['uygulama']}/{r['platform']}): {json.dumps(once, ensure_ascii=False)} hata değildi"
                             + (f" — neden: {r['aciklama']}" if r["aciklama"] else "") + ". Benzerini raporlama.")
        parts.append("### Geçmiş düzeltmeler\n" + "\n".join(lines))

    return "\n\n".join(parts) if parts else "(henüz yok)"


def accuracy() -> dict:
    """Doğruluk metrikleri: kesinlik = onaylanan / (onaylanan + reddedilen); duyarlılık = otomatik onaylı / (otomatik onaylı + eksik)."""
    r = store.q("SELECT durum, json_extract(veri,'$.kaynak') AS kaynak, json_extract(veri,'$.hata_turu') AS tur, "
                "COUNT(*) AS n FROM bulgular GROUP BY durum, kaynak, tur")
    per: dict[str, dict] = {}
    for row in r:
        d = per.setdefault(row["tur"] or "?", {"onay": 0, "red": 0, "eksik": 0})
        if row["kaynak"] == "manuel":
            d["eksik"] += row["n"]
        elif row["durum"] == "onaylandi":
            d["onay"] += row["n"]
        elif row["durum"] == "reddedildi":
            d["red"] += row["n"]
    out = {}
    for tur, d in per.items():
        kes = d["onay"] / (d["onay"] + d["red"]) if d["onay"] + d["red"] else None
        duy = d["onay"] / (d["onay"] + d["eksik"]) if d["onay"] + d["eksik"] else None
        out[tur] = {**d, "kesinlik": kes, "duyarlilik": duy}
    return out
