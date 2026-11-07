"""Yapay zekâ değerlendirici: kanıt + kontroller + öğrenilmiş kurallar -> bulgular."""
from __future__ import annotations

import json
from pathlib import Path

from .. import learning, llm
from ..config import catalog, read_text, settings


def findings_schema(names: list[str]) -> dict:
    item = {
        "type": "object",
        "properties": {
            "baslik": {"type": "string"},
            "hata_turu": {"type": "string", "enum": names} if names else {"type": "string"},
            "wcag": {"type": "array", "items": {"type": "string"}},
            "seviye": {"type": "string"},
            "not": {"type": "string"},
            "cozum_onerisi": {"type": "string"},
            "ekran": {"type": "string"},
            "onem": {"type": "string", "enum": ["Yüksek", "Orta", "Düşük"]},
            "guven": {"type": "number"},
            "baslangic_sn": {"type": "number"},
            "bitis_sn": {"type": "number"},
            "adim": {"type": "integer"},
            "soylenen": {"type": "string"},
            "kontrol_id": {"type": "string"},
        },
        "required": ["baslik", "hata_turu", "not", "cozum_onerisi", "onem", "guven"],
    }
    return {"type": "object", "properties": {"bulgular": {"type": "array", "items": item}}, "required": ["bulgular"]}


def build_prompt(uygulama: str, platform: str, checks: list[dict], kanitlar: str, adaylar: list[dict]) -> str:
    cat = catalog()
    hata_turleri = "\n".join(f"- {h['ad']} (WCAG {', '.join(h.get('wcag', []))}, {h.get('seviye', '')}): {h.get('aciklama', '')}"
                             for h in cat)
    kontroller = "\n".join(f"- [{c['id']}] ({c.get('hata_turu', '')}) {c.get('talimat', '').strip()}"
                           for c in checks if c.get("tur") == "llm") or "(yok)"
    aday_txt = json.dumps(adaylar, ensure_ascii=False, indent=1) if adaylar else "(yok)"
    tpl = read_text("prompts/analiz.md")
    rep = {
        "{uygulama}": uygulama, "{platform}": platform, "{dil}": settings().get("dil", "tr"),
        "{hata_turleri}": hata_turleri, "{kontroller}": kontroller,
        "{ogrenilenler}": learning.prompt_context(uygulama, platform),
        "{adaylar}": aday_txt, "{kanitlar}": kanitlar,
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    return tpl


def judge(uygulama: str, platform: str, checks: list[dict], kanitlar: str, images: list[Path],
          adaylar: list[dict], workdir: Path) -> list[dict]:
    names = [h["ad"] for h in catalog()]
    prompt = build_prompt(uygulama, platform, checks, kanitlar, adaylar)
    (workdir / "son_istem.md").write_text(prompt, encoding="utf-8")  # şeffaflık / hata ayıklama
    res = llm.structured(prompt, findings_schema(names), images=images, workdir=workdir)
    out = res.get("bulgular", [])
    for f in out:
        f["kaynak"] = "otomatik"
    return out


def video_evidence(segments: list[dict], frames: list[dict]) -> str:
    lines = ["### Ekran okuyucunun söyledikleri (konuşma tanıma çıktısı; kısa sözlerde hatalı olabilir)"]
    for s in segments:
        lines.append(f"[{s['start']:.1f}–{s['end']:.1f} sn] \"{s['text']}\"")
    if not segments:
        lines.append("(konuşma algılanmadı)")
    lines.append("Not: Türkçe ekran okuyucu sesi İngilizce etiketleri Türkçe fonetikle okur; konuşma tanıma bunları anlamsız "
                 "Türkçe sözcükler olarak yazabilir (ör. \"Back arrow\" → \"bekeroğu\"). Transkripti odaklanan öğeyle birlikte yorumla.")
    lines.append("\n### Ekran görüntüleri (her biri o andaki odak çerçevesini gösterir)")
    lines += [f"- {Path(f['yol']).name}: t={f['t']} sn" for f in frames]
    return "\n".join(lines)


def steps_evidence(steps: list[dict]) -> str:
    lines = []
    for st in steps:
        lines.append(f"### Adım {st['adim']} — Ekran: {st.get('ekran', '')} — görüntü: {Path(st['goruntu']).name}")
        lines.append("Ekran okuyucu okuma sırası (sırayla odaklanacak öğeler; [x,y,g,y] konum):")
        for i, o in enumerate(st.get("ogeler", []), 1):
            parts = [o.get("etiket") or "(etiketsiz)"]
            if o.get("deger"):
                parts.append(o["deger"])
            parts.append(o.get("rol") or o.get("tur", ""))
            if o.get("baslik"):
                parts.append("başlık")
            lines.append(f"  {i}. \"{', '.join(p for p in parts if p)}\" [{o.get('x')},{o.get('y')},{o.get('w')},{o.get('h')}]"
                         + (f" görünen metin: \"{o['metin']}\"" if o.get("metin") and o.get("metin") != o.get("etiket") else ""))
        if st.get("okunan"):
            lines.append("Gerçek ekran okuyucu çıktısı: " + " | ".join(st["okunan"]))
        lines.append("")
    return "\n".join(lines)
