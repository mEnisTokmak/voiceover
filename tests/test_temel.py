"""Telefon gerektirmeyen birim testleri.  Çalıştır:  docker compose run --rm -v "$PWD/tests:/tests" auditor python -m unittest discover -s /tests -v"""
import re
import unittest
import xml.etree.ElementTree as ET

from auditor.analysis import rules
from auditor.config import checks
from auditor.device.session import Blocked, parse_android, parse_ios

IOS_XML = """<AppiumAUT><XCUIElementTypeApplication name="Pegasus" accessible="false" visible="true" x="0" y="0" width="390" height="844">
  <XCUIElementTypeButton type="XCUIElementTypeButton" label="Back arrow" name="back_arrow" accessible="true" visible="true" x="8" y="50" width="20" height="20"/>
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" label="Seçili uçuşlar" name="Seçili uçuşlar" accessible="true" visible="true" x="120" y="50" width="150" height="24" traits="StaticText"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" label="ic_edit" name="ic_edit" accessible="true" visible="true" x="300" y="100" width="44" height="44"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" label="Seç" accessible="true" visible="true" x="20" y="400" width="80" height="44"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" label="Seç" accessible="true" visible="true" x="20" y="500" width="80" height="44"/>
  <XCUIElementTypeStaticText label="Gizli" accessible="true" visible="false" x="0" y="0" width="10" height="10"/>
</XCUIElementTypeApplication></AppiumAUT>"""

ANDROID_XML = """<hierarchy>
 <node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" displayed="true">
  <node class="android.widget.ImageButton" content-desc="Navigate up" clickable="true" bounds="[0,100][147,247]" displayed="true"/>
  <node class="android.widget.TextView" text="Uçuş Ara" heading="false" bounds="[200,120][700,200]" displayed="true"/>
  <node class="android.view.ViewGroup" clickable="true" bounds="[40,400][1040,700]" displayed="true">
    <node class="android.widget.TextView" text="12:00" bounds="[60,420][200,470]" displayed="true"/>
    <node class="android.widget.TextView" text="İstanbul" bounds="[60,480][300,530]" displayed="true"/>
  </node>
  <node class="android.widget.ImageView" clickable="true" bounds="[900,800][950,850]" displayed="true"/>
 </node>
</hierarchy>"""


def ctx_steps(items, olcek=1.0):
    return {"steps": [{"adim": 1, "ekran": "Test", "ogeler": items, "olcek": olcek}], "platform": "ios"}


class TestAyristirma(unittest.TestCase):
    def test_ios(self):
        items = parse_ios(ET.fromstring(IOS_XML), all_items=False)
        labels = [o["etiket"] for o in items]
        self.assertEqual(labels, ["Back arrow", "Seçili uçuşlar", "ic_edit", "Seç", "Seç"])  # gizli öğe yok, sıra korunur
        self.assertFalse(items[1]["baslik"])  # traits var ama Header yok

    def test_android_grup_birlestirme(self):
        items = parse_android(ET.fromstring(ANDROID_XML), all_items=False)
        labels = [o["etiket"] for o in items]
        self.assertIn("12:00, İstanbul", labels)  # tıklanabilir kart alt metinleri tek öğe
        self.assertNotIn("12:00", labels)
        self.assertIn("Navigate up", labels)


class TestKurallar(unittest.TestCase):
    def setUp(self):
        self.checks = checks()
        self.ios = parse_ios(ET.fromstring(IOS_XML), all_items=False)

    def bul(self, kontrol_id, ctx):
        return [f for f in rules.run(self.checks, ctx) if f["kontrol_id"] == kontrol_id]

    def test_dil_agac(self):
        f = self.bul("dil_ozelligi", ctx_steps(self.ios))
        self.assertTrue(any("Back arrow" in x["soylenen"] for x in f))

    def test_dil_fonetik_transkript(self):
        ctx = {"segments": [{"start": 3.9, "end": 4.6, "text": "bekeroğu", "dil": "tr", "dil_olasilik": 0.5}]}
        f = self.bul("dil_ozelligi", ctx)
        self.assertEqual(len(f), 1)
        self.assertIn("back arrow", f[0]["baslik"])

    def test_dil_turkce_temiz(self):
        ctx = {"segments": [{"start": 0, "end": 1, "text": "Düzenle, düğme", "dil": "fr", "dil_olasilik": 0.65}]}
        self.assertEqual(self.bul("dil_ozelligi", ctx), [])  # yalnız ses dili tahmini bulgu üretmez

    def test_anlamsiz_etiket(self):
        f = self.bul("anlamsiz_etiket", ctx_steps(self.ios))
        self.assertTrue(any(x["soylenen"] == "ic_edit" for x in f))

    def test_dokunma_hedefi(self):
        f = self.bul("dokunma_hedefi", ctx_steps(self.ios))
        self.assertEqual([x["soylenen"] for x in f], ["Back arrow"])  # 20x20 pt

    def test_dokunma_hedefi_android_dp(self):
        items = parse_android(ET.fromstring(ANDROID_XML), all_items=False)
        f = self.bul("dokunma_hedefi", ctx_steps(items, olcek=2.625))  # 50px / 2.625 = 19dp
        self.assertEqual(len(f), 1)

    def test_tekrar_eden(self):
        f = self.bul("tekrar_eden_etiket", ctx_steps(self.ios))
        self.assertEqual(len(f), 1)


class TestGuvenlik(unittest.TestCase):
    def test_yasakli(self):
        from auditor.device.session import DeviceSession
        d = DeviceSession.__new__(DeviceSession)
        d.forbidden = [re.compile(x, re.I) for x in ["öde", "satın al", "rezervasyonu (onayla|tamamla)"]]
        with self.assertRaises(Blocked):
            d._guard("Ödemeyi tamamla ve Öde")
        with self.assertRaises(Blocked):
            d._guard("Rezervasyonu Onayla")
        d._guard("Uçuş Ara")  # hata vermemeli


if __name__ == "__main__":
    unittest.main()
