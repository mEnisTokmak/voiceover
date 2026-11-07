"""Kural motoru: ölçülebilir kontroller. checks.yaml'daki `tur: kural` maddeleri buradaki fonksiyonlara bağlanır.

Yeni hazır kural eklemek: aşağıya `@rule("ad")` ile bir fonksiyon yazın, checks.yaml'da `kural: ad` ile kullanın.

ctx = {
  "segments": [{start,end,text,dil,dil_olasilik,kelimeler}],   # video sesinden (varsa)
  "steps":    [{adim, ekran, ogeler:[{etiket,deger,metin,tur,baslik,tiklanabilir,x,y,w,h}], olcek}],  # ajan oturumundan
  "platform": "ios" | "android",
}
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable

RULES: dict[str, Callable[[dict, dict], list[dict]]] = {}


def rule(name: str):
    def deco(fn):
        RULES[name] = fn
        return fn
    return deco


def run(checks: list[dict], ctx: dict) -> list[dict]:
    out: list[dict] = []
    for c in checks:
        if c.get("tur") != "kural":
            continue
        fn = RULES.get(c.get("kural", ""))
        if not fn:
            continue
        for f in fn(c.get("parametreler") or {}, ctx):
            f.setdefault("hata_turu", c.get("hata_turu", ""))
            f.setdefault("guven", c.get("guven", 0.8))
            f["kontrol_id"] = c["id"]
            f["kaynak"] = "otomatik"
            out.append(f)
    return out


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]+", text.lower())


def _english_hits(text: str, vocab: list[str]) -> list[str]:
    toks = _tokens(text)
    joined = " " + " ".join(toks) + " "
    return [v for v in vocab if f" {v} " in joined]


@rule("dil")
def dil(p: dict, ctx: dict) -> list[dict]:
    beklenen = p.get("beklenen_dil", "tr")
    esik = p.get("dil_olasilik_esigi", 0.6)
    vocab = [v.lower() for v in p.get("ingilizce_kelimeler", [])]
    fonetik = {k: re.compile(v, re.I) for k, v in (p.get("fonetik_kaliplar") or {}).items()}
    out = []
    for s in ctx.get("segments", []):
        metinler = s["text"]
        hits = _english_hits(metinler, vocab)
        hits += [f"{en} (Türkçe okunuşu: \"{m.group(0)}\")" for en, rx in fonetik.items() if (m := rx.search(metinler))]
        # Ses dili tahmini kısa sözlerde güvenilmez: tek başına bulgu üretmesi parametreyle açılır.
        yanlis_dil = (p.get("yalniz_ses_dili_ile_raporla", False) and s.get("dil") and s["dil"] != beklenen
                      and s.get("dil_olasilik", 0) >= esik)
        if hits or yanlis_dil:
            neden = []
            if yanlis_dil:
                neden.append(f"konuşma dili '{s['dil']}' olarak algılandı (olasılık {s.get('dil_olasilik')})")
            if hits:
                neden.append(f"İngilizce kelime(ler): {', '.join(hits)}")
            ilk = hits[0].split(" (")[0] if hits else ""
            out.append({
                "baslik": f"Ekran okuyucu \"{ilk}\" ifadesini İngilizce okuyor" if ilk else f"\"{s['text'][:40]}\" yanlış dilde okunuyor",
                "not": f"Ekran okuyucu \"{s['text']}\" diyor; {'; '.join(neden)}. Beklenen dil: {beklenen}.",
                "soylenen": s["text"], "baslangic_sn": s["start"], "bitis_sn": s["end"], "adim": 0,
            })
    for st in ctx.get("steps", []):
        for o in st.get("ogeler", []):
            hits = _english_hits(o.get("etiket", ""), vocab)
            if hits:
                out.append({
                    "baslik": f"{st.get('ekran', '')}: \"{o['etiket']}\" etiketi İngilizce",
                    "not": f"Öğenin erişilebilir adı \"{o['etiket']}\" (İngilizce: {', '.join(hits)}). Beklenen dil: {beklenen}.",
                    "soylenen": o["etiket"], "ekran": st.get("ekran", ""), "adim": st["adim"],
                    "baslangic_sn": st.get("t", 0), "bitis_sn": st.get("t", 0),
                })
    return out


@rule("anlamsiz_etiket")
def anlamsiz_etiket(p: dict, ctx: dict) -> list[dict]:
    pats = [re.compile(k, re.I) for k in p.get("kaliplar", [])]
    out = []
    for st in ctx.get("steps", []):
        for o in st.get("ogeler", []):
            et = (o.get("etiket") or "").strip()
            if et and any(pt.search(et) for pt in pats):
                out.append({"baslik": f"{st.get('ekran', '')}: anlamsız etiket \"{et}\"",
                            "not": f"Öğe ekran okuyucuda \"{et}\" olarak okunuyor; işlevini anlatmıyor.",
                            "soylenen": et, "ekran": st.get("ekran", ""), "adim": st["adim"]})
            elif p.get("etiketsiz_tiklanabilir", True) and o.get("tiklanabilir") and not et and not o.get("metin"):
                out.append({"baslik": f"{st.get('ekran', '')}: etiketsiz etkileşimli öğe",
                            "not": f"Tıklanabilir öğenin ({o.get('tur')}, konum {o.get('x')},{o.get('y')}) erişilebilir adı yok.",
                            "ekran": st.get("ekran", ""), "adim": st["adim"]})
    return out


@rule("dokunma_hedefi")
def dokunma_hedefi(p: dict, ctx: dict) -> list[dict]:
    mn = p.get("en_kucuk_pt", 24)
    out = []
    for st in ctx.get("steps", []):
        olcek = st.get("olcek", 1.0) or 1.0
        for o in st.get("ogeler", []):
            w, h = (o.get("w") or 0) / olcek, (o.get("h") or 0) / olcek
            if o.get("tiklanabilir") and 0 < min(w, h) < mn:
                out.append({"baslik": f"{st.get('ekran', '')}: \"{o.get('etiket') or o.get('tur')}\" dokunma hedefi küçük",
                            "not": f"Dokunma alanı {w:.0f}x{h:.0f} pt; en az {mn}x{mn} pt olmalı.",
                            "soylenen": o.get("etiket", ""), "ekran": st.get("ekran", ""), "adim": st["adim"]})
    return out


@rule("tekrar_eden_etiket")
def tekrar_eden_etiket(p: dict, ctx: dict) -> list[dict]:
    out = []
    for st in ctx.get("steps", []):
        cnt = Counter((o.get("etiket") or "").strip() for o in st.get("ogeler", []) if o.get("tiklanabilir"))
        for et, n in cnt.items():
            if et and n > 1:
                out.append({"baslik": f"{st.get('ekran', '')}: {n} farklı öğe aynı \"{et}\" etiketine sahip",
                            "not": f"{n} etkileşimli öğe \"{et}\" olarak okunuyor; kullanıcı aralarındaki farkı anlayamaz.",
                            "soylenen": et, "ekran": st.get("ekran", ""), "adim": st["adim"]})
    return out
