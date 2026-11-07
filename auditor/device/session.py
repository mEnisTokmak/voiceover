"""Telefon oturumu (Appium) ve ajan araçları.

Aynı araçlar iki yerden kullanılır:
  - CLI arka ucu: mcp_server.py bu araçları MCP üzerinden Claude Code'a açar
  - API arka ucu: agent.py araçları doğrudan Messages API tool-use döngüsünde çağırır
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import store
from ..config import app_profile, settings

TOOL_SPECS = [
    {"name": "ekran_goruntusu", "description": "Telefonun güncel ekran görüntüsünü al.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "ogeler", "description": "Ekrandaki öğeleri listele (indeks, etiket, rol, konum). Dokunmak için indeks kullan.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "dokun", "description": "ogeler listesindeki indeksi verilen öğeye dokun.",
     "input_schema": {"type": "object", "properties": {"indeks": {"type": "integer"}}, "required": ["indeks"]}},
    {"name": "dokun_koordinat", "description": "Cihaz koordinatına dokun (ogeler'deki konum birimiyle).",
     "input_schema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
    {"name": "yaz", "description": "Bir metin alanına yaz. indeks verilirse önce o alana dokunur.",
     "input_schema": {"type": "object", "properties": {"metin": {"type": "string"}, "indeks": {"type": "integer"}}, "required": ["metin"]}},
    {"name": "kaydir", "description": "Ekranı kaydır. yon: asagi | yukari | sola | saga (asagi = içerikte aşağı ilerle).",
     "input_schema": {"type": "object", "properties": {"yon": {"type": "string", "enum": ["asagi", "yukari", "sola", "saga"]}}, "required": ["yon"]}},
    {"name": "geri", "description": "Bir önceki ekrana dön.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "ekran_okuyucu_taramasi",
     "description": "Bu ekranı ekran okuyucu gözüyle baştan sona tara ve analiz için kaydet. Her yeni ekranda bir kez çağır.",
     "input_schema": {"type": "object", "properties": {"ekran_adi": {"type": "string"}}, "required": ["ekran_adi"]}},
    {"name": "bitir", "description": "Senaryo bitti; kısa özetle oturumu kapat.",
     "input_schema": {"type": "object", "properties": {"ozet": {"type": "string"}}, "required": ["ozet"]}},
]

IOS_ROLES = {"Button": "düğme", "Link": "bağlantı", "TextField": "metin alanı", "SecureTextField": "parola alanı",
             "Switch": "anahtar", "Slider": "kaydırıcı", "Image": "görsel", "SearchField": "arama alanı",
             "Tab": "sekme", "SegmentedControl": "bölümlü denetim", "Cell": "", "StaticText": "", "Other": ""}
IOS_CLICKABLE = {"Button", "Link", "Cell", "Switch", "TextField", "SecureTextField", "SearchField", "Tab", "SegmentedControl", "Slider"}


class Blocked(Exception):
    pass


class DeviceSession:
    def __init__(self, aid: str, platform: str, app: str):
        self.aid, self.platform, self.app = aid, platform.lower(), app
        self.profile = app_profile(app)
        self.sdir = store.session_path(aid)
        (self.sdir / "adimlar").mkdir(exist_ok=True)
        (self.sdir / "goruntuler").mkdir(exist_ok=True)
        self.forbidden = [re.compile(x, re.I) for x in self.profile.get("yasakli_eylemler", [])]
        self.driver = None
        self.t0: float | None = None
        self.items: list[dict] = []
        self.step_no = len(list((self.sdir / "adimlar").glob("adim_*.json")))
        self.scanned: set[str] = set()
        self.olcek = 1.0
        self.done = False

    # ------------------------------------------------------------ bağlantı
    def connect(self) -> None:
        if self.driver:
            return
        from appium import webdriver
        url = settings()["appium"]["url"]
        if self.platform == "ios":
            from appium.options.ios import XCUITestOptions
            p = self.profile["ios"]
            o = XCUITestOptions()
            o.bundle_id = p["bundleId"]
            if p.get("udid"):
                o.udid = p["udid"]
        else:
            from appium.options.android import UiAutomator2Options
            p = self.profile["android"]
            o = UiAutomator2Options()
            o.app_package = p["appPackage"]
            if p.get("appActivity"):
                o.app_activity = p["appActivity"]
            if p.get("udid"):
                o.udid = p["udid"]
            o.set_capability("appium:autoGrantPermissions", True)
        o.no_reset = True
        o.new_command_timeout = 900
        store.log(self.aid, f"Telefona bağlanılıyor: {url} ({self.platform})")
        self.driver = webdriver.Remote(url, options=o)
        if self.platform == "android":
            try:
                self.olcek = float(self.driver.get_display_density()) / 160.0
            except Exception:
                self.olcek = 1.0
        try:
            self.driver.start_recording_screen(timeLimit="1800")
        except Exception as e:
            store.log(self.aid, f"Ekran kaydı başlatılamadı (klipler olmadan devam): {e}")
        self.t0 = time.time()

    def close(self) -> None:
        if not self.driver:
            return
        try:
            data = self.driver.stop_recording_screen()
            if data:
                (self.sdir / "kayit.mp4").write_bytes(base64.b64decode(data))
        except Exception as e:
            store.log(self.aid, f"Ekran kaydı alınamadı: {e}")
        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None

    def t(self) -> float:
        return round(time.time() - self.t0, 2) if self.t0 else 0.0

    # ------------------------------------------------------------ araç dağıtıcı
    def call(self, name: str, args: dict) -> str | dict:
        self.connect()
        try:
            fn = getattr(self, f"tool_{name}")
            return fn(**(args or {}))
        except Blocked as e:
            store.log(self.aid, f"ENGELLENDİ: {e}")
            return f"ENGELLENDİ: {e}. Bu eylem güvenlik nedeniyle yasak; başka yol dene veya bitir."
        except Exception as e:
            return f"HATA: {type(e).__name__}: {e}"

    # ------------------------------------------------------------ araçlar
    def tool_ekran_goruntusu(self) -> dict:
        return {"image": str(self._screenshot(f"anlik_{int(time.time() * 1000)}"))}

    def tool_ogeler(self) -> str:
        self.items = self._parse(all_items=True)
        lines = [f"{i}: \"{o['etiket'] or o['metin'] or '(etiketsiz)'}\" {o['rol'] or o['tur']}"
                 f"{' [tıklanabilir]' if o['tiklanabilir'] else ''} @{o['x']},{o['y']} {o['w']}x{o['h']}"
                 for i, o in enumerate(self.items)]
        return "\n".join(lines) or "(öğe bulunamadı)"

    def tool_dokun(self, indeks: int) -> str:
        if not self.items:
            self.items = self._parse(all_items=True)
        o = self.items[indeks]
        self._guard(f"{o['etiket']} {o['metin']}")
        self._tap(o["x"] + o["w"] / 2, o["y"] + o["h"] / 2)
        time.sleep(1.2)
        self.items = []
        return f"Dokunuldu: \"{o['etiket'] or o['metin']}\""

    def tool_dokun_koordinat(self, x: int, y: int) -> str:
        for o in sorted(self._parse(all_items=True), key=lambda o: o["w"] * o["h"]):
            if o["x"] <= x <= o["x"] + o["w"] and o["y"] <= y <= o["y"] + o["h"]:
                self._guard(f"{o['etiket']} {o['metin']}")
                break
        self._tap(x, y)
        time.sleep(1.2)
        self.items = []
        return f"Dokunuldu: {x},{y}"

    def tool_yaz(self, metin: str, indeks: int | None = None) -> str:
        if indeks is not None:
            self.tool_dokun(indeks)
        self.driver.switch_to.active_element.send_keys(metin)
        return f"Yazıldı: {metin}"

    def tool_kaydir(self, yon: str) -> str:
        size = self.driver.get_window_size()
        w, h = size["width"], size["height"]
        cx, cy = w / 2, h / 2
        moves = {"asagi": (cx, h * 0.75, cx, h * 0.3), "yukari": (cx, h * 0.3, cx, h * 0.75),
                 "sola": (w * 0.8, cy, w * 0.2, cy), "saga": (w * 0.2, cy, w * 0.8, cy)}
        self._swipe(*moves[yon])
        time.sleep(0.8)
        self.items = []
        return f"Kaydırıldı: {yon}"

    def tool_geri(self) -> str:
        self.driver.back()
        time.sleep(1.0)
        self.items = []
        return "Geri gidildi"

    def tool_ekran_okuyucu_taramasi(self, ekran_adi: str) -> str:
        if ekran_adi in self.scanned:
            return f"\"{ekran_adi}\" zaten tarandı."
        t_start = self.t()
        self.step_no += 1
        img = self._screenshot(f"adim_{self.step_no:03d}")
        ogeler = self._parse(all_items=False)
        step = {"adim": self.step_no, "ekran": ekran_adi, "t": t_start, "t_bitis": self.t(),
                "goruntu": str(img), "ogeler": ogeler, "olcek": self.olcek, "platform": self.platform}
        (self.sdir / "adimlar" / f"adim_{self.step_no:03d}.json").write_text(
            json.dumps(step, ensure_ascii=False, indent=1), encoding="utf-8")
        self.scanned.add(ekran_adi)
        store.log(self.aid, f"Tarandı: adım {self.step_no} — {ekran_adi} ({len(ogeler)} öğe)")
        okunan = [", ".join(x for x in [o["etiket"] or "(etiketsiz)", o["rol"], "başlık" if o["baslik"] else ""] if x)
                  for o in ogeler[:40]]
        return f"Tarama kaydedildi ({len(ogeler)} öğe). Okuma sırası: " + " | ".join(okunan)

    def tool_bitir(self, ozet: str) -> str:
        store.log(self.aid, f"Ajan bitirdi: {ozet}")
        self.done = True
        self.close()
        return "Oturum kapatıldı."

    # ------------------------------------------------------------ yardımcılar
    def _guard(self, text: str) -> None:
        for pat in self.forbidden:
            if pat.search(text or ""):
                raise Blocked(f"\"{text.strip()}\" yasaklı eylem kalıbına uyuyor ({pat.pattern})")

    def _screenshot(self, name: str) -> Path:
        png = self.sdir / "goruntuler" / f"{name}.png"
        png.write_bytes(self.driver.get_screenshot_as_png())
        jpg = png.with_suffix(".jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(png), "-vf", "scale=540:-2", "-q:v", "3", str(jpg)],
                       check=False)
        if jpg.exists():
            png.unlink()
            return jpg
        return png

    def _actions(self):
        from selenium.webdriver.common.actions import interaction
        from selenium.webdriver.common.actions.action_builder import ActionBuilder
        from selenium.webdriver.common.actions.pointer_input import PointerInput
        finger = PointerInput(interaction.POINTER_TOUCH, "finger")
        return ActionBuilder(self.driver, mouse=finger, duration=350)

    def _tap(self, x: float, y: float) -> None:
        ab = self._actions()
        ab.pointer_action.move_to_location(int(x), int(y))
        ab.pointer_action.pointer_down()
        ab.pointer_action.pause(0.08)
        ab.pointer_action.pointer_up()
        ab.perform()

    def _swipe(self, x1, y1, x2, y2) -> None:
        ab = self._actions()
        ab.pointer_action.move_to_location(int(x1), int(y1))
        ab.pointer_action.pointer_down()
        ab.pointer_action.move_to_location(int(x2), int(y2))
        ab.pointer_action.pointer_up()
        ab.perform()

    def _parse(self, all_items: bool) -> list[dict]:
        """Erişilebilirlik ağacı -> ekran okuyucunun okuyacağı öğeler (all_items=False) veya tüm etkileşimli öğeler."""
        root = ET.fromstring(self.driver.page_source.encode("utf-8"))
        return parse_ios(root, all_items) if self.platform == "ios" else parse_android(root, all_items)


def parse_ios(root: ET.Element, all_items: bool) -> list[dict]:
    out = []
    for el in root.iter():
        a = el.attrib
        if not el.tag.startswith("XCUIElementType") or el.tag == "XCUIElementTypeApplication":
            continue
        if a.get("visible") == "false":
            continue
        typ = el.tag.replace("XCUIElementType", "")
        accessible = a.get("accessible") == "true"
        clickable = typ in IOS_CLICKABLE
        if not (accessible or (all_items and clickable)):
            continue
        traits = a.get("traits", "")
        out.append({
            "etiket": a.get("label") or "", "deger": a.get("value") or "", "metin": a.get("name") or "",
            "tur": typ, "rol": IOS_ROLES.get(typ, ""), "tiklanabilir": clickable,
            "baslik": ("Header" in traits) if traits else (typ == "NavigationBar" or None),
            "secili": a.get("selected") == "true",
            "x": int(float(a.get("x", 0))), "y": int(float(a.get("y", 0))),
            "w": int(float(a.get("width", 0))), "h": int(float(a.get("height", 0))),
        })
    return out


def _bounds(b: str) -> tuple[int, int, int, int]:
    m = re.findall(r"\d+", b or "")
    if len(m) != 4:
        return 0, 0, 0, 0
    x1, y1, x2, y2 = map(int, m)
    return x1, y1, x2 - x1, y2 - y1


def parse_android(root: ET.Element, all_items: bool) -> list[dict]:
    """TalkBack yaklaşımı: tıklanabilir/odaklanabilir kapsayıcı, etiketsizse alt öğelerin metinlerini birleştirip tek öğe olarak okunur."""
    out: list[dict] = []

    def texts(n: ET.Element) -> list[str]:
        r = []
        for c in n.iter():
            t = c.attrib.get("content-desc") or c.attrib.get("text")
            if t:
                r.append(t)
        return r

    def visit(n: ET.Element) -> None:
        a = n.attrib
        if a.get("displayed") == "false":
            return
        cls = (a.get("class") or "").split(".")[-1]
        clickable = a.get("clickable") == "true" or a.get("long-clickable") == "true"
        focusable = a.get("focusable") == "true" or a.get("screen-reader-focusable") == "true"
        own = a.get("content-desc") or a.get("text") or ""
        if n.tag != "hierarchy" and (clickable or focusable):
            label = own or ", ".join(texts(n))
            x, y, w, h = _bounds(a.get("bounds"))
            out.append({"etiket": a.get("content-desc") or label, "deger": a.get("state-description") or "",
                        "metin": a.get("text") or label, "tur": cls,
                        "rol": "düğme" if "Button" in cls or clickable else "", "tiklanabilir": clickable,
                        "baslik": (a.get("heading") == "true") if "heading" in a else None,
                        "secili": a.get("selected") == "true" or a.get("checked") == "true",
                        "x": x, "y": y, "w": w, "h": h})
            return  # TalkBack alt öğeleri bu öğe içinde okur
        if n.tag != "hierarchy" and own:
            x, y, w, h = _bounds(a.get("bounds"))
            out.append({"etiket": own, "deger": "", "metin": a.get("text") or "", "tur": cls, "rol": "",
                        "tiklanabilir": False, "baslik": (a.get("heading") == "true") if "heading" in a else None,
                        "secili": False, "x": x, "y": y, "w": w, "h": h})
        for c in n:
            visit(c)

    visit(root)
    return out
