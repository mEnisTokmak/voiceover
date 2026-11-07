"""Analiz boru hattı: video veya ajan oturumu -> bulgular (beklemede) + klipler."""
from __future__ import annotations

import json
from pathlib import Path

from .. import llm, store
from ..config import catalog_by_name, checks, settings
from . import judge, media, rules, transcribe


def _finalize(f: dict, platform: str) -> dict:
    """Katalogdan eksik alanları doldur."""
    cat = catalog_by_name().get(f.get("hata_turu", ""), {})
    f.setdefault("wcag", cat.get("wcag", []))
    if not f.get("wcag"):
        f["wcag"] = cat.get("wcag", [])
    if not f.get("seviye"):
        f["seviye"] = cat.get("seviye", "")
    if not f.get("cozum_onerisi"):
        f["cozum_onerisi"] = cat.get(f"cozum_{platform}", "")
    f.setdefault("onem", "Orta")
    f["platform"] = platform
    for k in ("baslangic_sn", "bitis_sn"):
        f[k] = float(f.get(k) or 0)
    f["adim"] = int(f.get("adim") or 0)
    return f


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in sorted(items, key=lambda x: -float(x.get("guven", 0))):
        key = (f.get("hata_turu"), f.get("adim", 0), round(float(f.get("baslangic_sn") or 0)), (f.get("soylenen") or f.get("baslik", "")).lower()[:40])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return sorted(out, key=lambda x: (x.get("adim", 0), x.get("baslangic_sn", 0)))


def _drop_decided(aid: str, items: list[dict]) -> list[dict]:
    """Yeniden analizde, denetçinin zaten onayladığı/reddettiği bulgularla örtüşenleri tekrar önerme."""
    decided = [f["veri"] for f in store.findings(aid) if f["durum"] != "beklemede"]
    out = []
    for f in items:
        dup = any(d.get("hata_turu") == f.get("hata_turu") and d.get("adim", 0) == f.get("adim", 0)
                  and abs(float(d.get("baslangic_sn") or 0) - float(f.get("baslangic_sn") or 0)) <= 1.5
                  for d in decided)
        if not dup:
            out.append(f)
    return out


def _judge_batches(aid, audit, active, batches) -> list[dict]:
    """batches: [(kanit_metni, görseller, adaylar)]. Yapay zekâ kapalıysa/hata verirse adaylar aynen döner."""
    out: list[dict] = []
    for i, (kanit, imgs, adaylar) in enumerate(batches, 1):
        if llm.backend_name() == "none":
            out += adaylar
            continue
        store.log(aid, f"Yapay zekâ değerlendirmesi {i}/{len(batches)} ({llm.backend_name()}, {len(imgs)} görsel)…")
        try:
            out += judge.judge(audit["uygulama"], audit["platform"], active, kanit, imgs, adaylar, store.session_path(aid))
        except Exception as e:  # yapay zekâ başarısızsa kural bulguları kaybolmasın
            store.log(aid, f"UYARI: yapay zekâ değerlendirmesi başarısız ({e}); kural adayları kullanılıyor.")
            out += adaylar
    return out


def analyze_video(aid: str) -> None:
    audit = store.get_audit(aid)
    sdir = store.session_path(aid)
    video = Path(audit["video_yolu"])
    s = settings()
    active = checks()
    store.set_audit(aid, durum="analiz ediliyor")
    store.clear_findings(aid)

    segments: list[dict] = []
    if media.has_audio(video):
        store.log(aid, "Ses ayrılıyor ve metne çevriliyor (whisper)…")
        audio = media.extract_audio(video, sdir / "ses.wav")
        segments = transcribe.transcribe(audio, cache=sdir / "transkript.json")
        store.log(aid, f"{len(segments)} konuşma parçası: " + " | ".join(x["text"] for x in segments)[:400])
    else:
        store.log(aid, "UYARI: videoda ses yok; dil/okuma kontrolleri yalnız görüntüden yapılacak.")

    frames = media.keyframes(video, segments, sdir / "kareler", s.get("video", {}).get("en_fazla_kare", 24))
    adaylar = rules.run(active, {"segments": segments, "platform": audit["platform"]})
    store.log(aid, f"Kural motoru: {len(adaylar)} aday.")

    per = s["llm"].get("kare_per_cagri", 10)
    batches = []
    for i in range(0, len(frames), per):
        fr = frames[i:i + per]
        t0 = fr[0]["t"] - 0.5
        t1 = frames[i + per]["t"] if i + per < len(frames) else 1e9
        segs = [x for x in segments if t0 <= x["start"] < t1]
        ad = [a for a in adaylar if t0 <= a.get("baslangic_sn", 0) < t1]
        batches.append((judge.video_evidence(segs, fr), [Path(f["yol"]) for f in fr], ad))

    found = _drop_decided(aid, _dedupe([_finalize(f, audit["platform"]) for f in _judge_batches(aid, audit, active, batches)]))
    pad = s.get("video", {}).get("klip_payi_sn", 3)
    (sdir / "klipler").mkdir(exist_ok=True)
    for n, f in enumerate(found, 1):
        klip = ""
        if f["bitis_sn"] > 0 or f["baslangic_sn"] > 0:
            klip = str(media.clip(video, f["baslangic_sn"], f["bitis_sn"], sdir / "klipler" / f"{n:03d}.mp4", pad))
        store.add_finding(aid, f, klip=klip)
    store.set_audit(aid, durum="incelemede")
    store.log(aid, f"Analiz bitti: {len(found)} bulgu incelemeye hazır.")


def analyze_agent_session(aid: str) -> None:
    audit = store.get_audit(aid)
    sdir = store.session_path(aid)
    s = settings()
    active = checks()
    store.set_audit(aid, durum="analiz ediliyor")
    store.clear_findings(aid)

    steps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((sdir / "adimlar").glob("adim_*.json"))]
    if not steps:
        store.set_audit(aid, durum="hata")
        store.log(aid, "Analiz edilecek tarama adımı yok.")
        return
    adaylar = rules.run(active, {"steps": steps, "platform": audit["platform"]})
    store.log(aid, f"{len(steps)} ekran taraması, kural motoru: {len(adaylar)} aday.")

    per = s["llm"].get("kare_per_cagri", 10)
    batches = []
    for i in range(0, len(steps), per):
        grp = steps[i:i + per]
        nums = {st["adim"] for st in grp}
        batches.append((judge.steps_evidence(grp), [Path(st["goruntu"]) for st in grp],
                        [a for a in adaylar if a.get("adim") in nums]))

    found = _drop_decided(aid, _dedupe([_finalize(f, audit["platform"]) for f in _judge_batches(aid, audit, active, batches)]))
    by_step = {st["adim"]: st for st in steps}
    video = sdir / "kayit.mp4"
    pad = s.get("video", {}).get("klip_payi_sn", 3)
    (sdir / "klipler").mkdir(exist_ok=True)
    for n, f in enumerate(found, 1):
        st = by_step.get(f["adim"])
        gorsel = st["goruntu"] if st else ""
        klip = ""
        if st and video.exists() and st.get("t") is not None:
            f["baslangic_sn"] = f["baslangic_sn"] or st["t"]
            f["bitis_sn"] = f["bitis_sn"] or st.get("t_bitis", st["t"])
            f.setdefault("ekran", st.get("ekran", ""))
            try:
                klip = str(media.clip(video, f["baslangic_sn"], f["bitis_sn"], sdir / "klipler" / f"{n:03d}.mp4", pad))
            except Exception as e:
                store.log(aid, f"Klip kesilemedi: {e}")
        store.add_finding(aid, f, klip=klip, gorsel=gorsel)
    store.set_audit(aid, durum="incelemede")
    store.log(aid, f"Analiz bitti: {len(found)} bulgu incelemeye hazır.")
