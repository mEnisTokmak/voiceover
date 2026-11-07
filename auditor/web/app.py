"""Kontrol paneli: denetim başlat, bulguları incele/düzelt (öğrenme), ayarları düzenle, Drive'a yükle."""
from __future__ import annotations

import shutil
import threading
import traceback
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .. import agent, learning, llm, store
from ..analysis import media, pipeline
from ..config import CONFIG_DIR, DATA_DIR, catalog, catalog_by_name, editable_files, list_apps, list_scenarios, settings
from ..report import drive

app = FastAPI(title="Erişilebilirlik Denetimi")
T = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
CALISAN = {"kuyrukta", "analiz ediliyor", "ajan çalışıyor"}


def _bg(aid: str, fn) -> None:
    def wrap():
        try:
            fn(aid)
        except Exception as e:
            store.log(aid, f"HATA: {e}\n{traceback.format_exc()[-1500:]}")
            store.set_audit(aid, durum="hata")
    threading.Thread(target=wrap, daemon=True).start()


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ------------------------------------------------------------------ ana sayfa
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return T.TemplateResponse(request, "index.html", {
        "audits": store.list_audits(), "apps": list_apps(), "scenarios": list_scenarios(),
        "backend": llm.backend_name(), "calisan": CALISAN, "appium": settings()["appium"]["url"],
    })


@app.post("/video")
async def video_yukle(uygulama: str = Form(...), platform: str = Form(...), dosya: UploadFile = File(...)):
    aid = store.create_audit(uygulama, platform, "video")
    dst = store.session_path(aid) / ("video" + Path(dosya.filename or "v.mp4").suffix)
    with open(dst, "wb") as f:
        shutil.copyfileobj(dosya.file, f)
    store.set_audit(aid, video_yolu=str(dst))
    store.log(aid, f"Video yüklendi: {dosya.filename}")
    _bg(aid, pipeline.analyze_video)
    return back(f"/denetim/{aid}")


@app.post("/ajan")
def ajan_baslat(uygulama: str = Form(...), platform: str = Form(...), senaryo: str = Form(""), serbest: str = Form("")):
    aid = store.create_audit(uygulama, platform, "ajan", senaryo=serbest.strip() or senaryo)
    _bg(aid, agent.run)
    return back(f"/denetim/{aid}")


# ------------------------------------------------------------------ denetim
@app.get("/denetim/{aid}", response_class=HTMLResponse)
def denetim(request: Request, aid: str):
    a = store.get_audit(aid)
    if not a:
        raise HTTPException(404)
    return T.TemplateResponse(request, "denetim.html", {
        "a": a, "bulgular": store.findings(aid), "turler": [h["ad"] for h in catalog()],
        "calisan": a["durum"] in CALISAN,
    })


@app.post("/denetim/{aid}/yeniden")
def yeniden(aid: str):
    a = store.get_audit(aid)
    store.log(aid, "Yeniden analiz (güncel kontroller ve öğrenilmiş kurallarla)…")
    _bg(aid, pipeline.analyze_video if a["tur"] == "video" else pipeline.analyze_agent_session)
    return back(f"/denetim/{aid}")


@app.post("/denetim/{aid}/drive")
def drive_yukle(aid: str):
    try:
        drive.upload_audit(aid)
    except Exception as e:
        store.log(aid, f"Drive hatası: {e}")
    return back(f"/denetim/{aid}")


def _form_finding(form) -> dict:
    tur = form.get("hata_turu", "")
    cat = catalog_by_name().get(tur, {})
    wcag = [w.strip() for w in (form.get("wcag") or "").split(",") if w.strip()] or cat.get("wcag", [])
    return {"baslik": form.get("baslik", "").strip(), "hata_turu": tur, "wcag": wcag,
            "seviye": form.get("seviye") or cat.get("seviye", ""), "not": form.get("not", "").strip(),
            "cozum_onerisi": form.get("cozum_onerisi", "").strip(), "ekran": form.get("ekran", "").strip(),
            "onem": form.get("onem", "Orta")}


@app.post("/bulgu/{fid}/kaydet")
async def bulgu_kaydet(request: Request, fid: int):
    form = await request.form()
    f = store.get_finding(fid)
    a = store.get_audit(f["denetim_id"])
    once = dict(f["veri"])
    sonra = {**once, **_form_finding(form)}
    learning.record_correction(a, fid, once, sonra, form.get("ders", ""))
    store.update_finding(fid, veri=sonra, durum="onaylandi")
    return back(f"/denetim/{a['id']}#b{fid}")


@app.post("/bulgu/{fid}/onayla")
def bulgu_onayla(fid: int):
    f = store.get_finding(fid)
    store.update_finding(fid, durum="onaylandi")
    return back(f"/denetim/{f['denetim_id']}#b{fid}")


@app.post("/bulgu/{fid}/reddet")
def bulgu_reddet(fid: int, neden: str = Form("")):
    f = store.get_finding(fid)
    a = store.get_audit(f["denetim_id"])
    learning.record_rejected(a, fid, f["veri"], neden)
    store.update_finding(fid, durum="reddedildi")
    return back(f"/denetim/{a['id']}#b{fid}")


@app.post("/bulgu/{fid}/geri_al")
def bulgu_geri_al(fid: int):
    f = store.get_finding(fid)
    store.update_finding(fid, durum="beklemede")
    return back(f"/denetim/{f['denetim_id']}#b{fid}")


@app.post("/denetim/{aid}/ekstra")
async def ekstra(request: Request, aid: str):
    form = await request.form()
    a = store.get_audit(aid)
    v = {**_form_finding(form), "platform": a["platform"], "kaynak": "manuel", "guven": 1.0}
    bas, bit = float(form.get("baslangic_sn") or 0), float(form.get("bitis_sn") or 0)
    v.update(baslangic_sn=bas, bitis_sn=bit)
    if not v["cozum_onerisi"]:
        v["cozum_onerisi"] = catalog_by_name().get(v["hata_turu"], {}).get(f"cozum_{a['platform']}", "")
    klip = ""
    video = Path(a["video_yolu"]) if a["video_yolu"] else store.session_path(aid) / "kayit.mp4"
    if (bas or bit) and video.exists():
        out = store.session_path(aid) / "klipler" / f"ekstra_{int(bas * 10)}.mp4"
        out.parent.mkdir(exist_ok=True)
        klip = str(media.clip(video, bas, bit or bas, out, settings().get("video", {}).get("klip_payi_sn", 3)))
    fid = store.add_finding(aid, v, klip=klip, durum="onaylandi")
    learning.record_missed(a, fid, v, form.get("ders", ""))
    return back(f"/denetim/{aid}#b{fid}")


@app.get("/dosya")
def dosya(yol: str):
    p = Path(yol).resolve()
    if not str(p).startswith(str(DATA_DIR.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


# ------------------------------------------------------------------ öğrenme
@app.get("/ogrenme", response_class=HTMLResponse)
def ogrenme(request: Request):
    duz = store.q("SELECT * FROM duzeltmeler ORDER BY id DESC LIMIT 100")
    return T.TemplateResponse(request, "ogrenme.html", {
        "dersler": learning.lessons(), "duzeltmeler": duz, "dogruluk": learning.accuracy(),
        "turler": [h["ad"] for h in catalog()],
    })


@app.post("/ders")
def ders_ekle(metin: str = Form(...), hata_turu: str = Form("")):
    learning.add_lesson(metin.strip(), hata_turu, "denetçi")
    return back("/ogrenme")


@app.post("/ders/{did}/guncelle")
def ders_guncelle(did: int, metin: str = Form(...), aktif: str = Form("0")):
    store.ex("UPDATE dersler SET metin=?, aktif=? WHERE id=?", (metin.strip(), 1 if aktif == "1" else 0, did))
    return back("/ogrenme")


@app.post("/ders/{did}/sil")
def ders_sil(did: int):
    store.ex("DELETE FROM dersler WHERE id=?", (did,))
    return back("/ogrenme")


# ------------------------------------------------------------------ ayarlar
@app.get("/ayarlar", response_class=HTMLResponse)
def ayarlar(request: Request, dosya: str = "checks.yaml", mesaj: str = ""):
    files = editable_files()
    if dosya not in files:
        raise HTTPException(404)
    return T.TemplateResponse(request, "ayarlar.html", {
        "dosyalar": files, "dosya": dosya, "icerik": (CONFIG_DIR / dosya).read_text(encoding="utf-8"), "mesaj": mesaj,
    })


@app.post("/ayarlar")
def ayarlar_kaydet(dosya: str = Form(...), icerik: str = Form(...), yeni_ad: str = Form("")):
    if yeni_ad.strip():  # yeni senaryo / uygulama dosyası
        dosya = yeni_ad.strip()
        if not any(dosya.startswith(p) for p in ("scenarios/", "apps/", "prompts/")) or ".." in dosya:
            return back("/ayarlar?mesaj=Yeni+dosya+scenarios/,+apps/+veya+prompts/+altında+olmalı")
    elif dosya not in editable_files():
        raise HTTPException(404)
    if dosya.endswith(".yaml"):
        try:
            yaml.safe_load(icerik)
        except yaml.YAMLError as e:
            return back(f"/ayarlar?dosya={dosya}&mesaj=YAML+hatası,+kaydedilmedi:+{str(e)[:150]}")
    (CONFIG_DIR / dosya).parent.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / dosya).write_text(icerik.replace("\r\n", "\n"), encoding="utf-8")
    return back(f"/ayarlar?dosya={dosya}&mesaj=Kaydedildi")
