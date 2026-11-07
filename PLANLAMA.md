# Proje Planı: Mobil Erişilebilirlik Otomatik Denetim Sistemi

**Başlangıç:** 9 Kasım 2026 (Pazartesi)
**Tahmini toplam süre:** 9–10 hafta (1 geliştirici, yarı otomatik inceleme dahil)
**Bağlı doküman:** [RAPOR.md](RAPOR.md)

---

## ⭐ Güncel durum (7 Kasım 2026): plan güncellendi

Plan onaylandı. İstenen değişiklik doğrultusunda **Faz 1 (video analizi), Faz 4 (ajan + panel) ve öğrenme tek aşamada birleştirildi ve kuruldu.** Öğrenme özelliği ayrı bir aşama gerektirecek kadar büyük değildi.

**Kurulan ve doğrulanan:**

| Bileşen | Durum | Doğrulama |
|---|---|---|
| Docker (panel + analiz + ajan + Drive tek imajda) | ✅ | `docker compose up` ile çalışıyor |
| Yapay zekâ arka ucu: `cli` / `api` / `none` (`.env` ile seçilir) | ✅ | `cli` 3 örnek videoda çalıştırıldı; `api` kodu yazıldı, anahtar olmadığı için çalıştırılmadı |
| Video analizi (whisper + kural motoru + Claude) | ✅ | 3 örnek videodaki 3 bilinen hatanın 3'ü de bulundu (ayrıntı: README) |
| Öğrenme (düzeltme / red / ekstra → kural + örnek) | ✅ | Bir bulgu gerekçeyle reddedildi; yeniden analizde aynı bulgu üretilmedi |
| Değiştirilebilir akış (checks.yaml, katalog, istemler, senaryolar, panel editörü) | ✅ | Panelden kaydetme ve YAML doğrulama test edildi |
| Ajan (Appium + MCP / API tool-use, yasaklı eylem engeli) | 🟡 Kod hazır | Birim testleri geçti; **gerçek telefonla henüz denenmedi** (bu Mac'te Appium/telefon yok) |
| Google Drive + Sheets yükleme | 🟡 Kod hazır | **Henüz denenmedi**: OAuth kimlik bilgisi gerekli |

**Sıradaki adımlar (eski Faz 0, 2, 3 ve 5'in kalanları):**
1. Telefon köprüsünü kur (`host/mac-kurulum.sh`), Pegasus paket/bundle adlarını doğrula, ajanı Android'de bir senaryoyla dene.
2. Aynısını iPhone'da dene. Gerçek VoiceOver hareketiyle tarama (`tarama_stratejisi`) bu testten sonra eklenecek.
3. Drive OAuth kurulumu ve ilk gerçek yükleme.
4. Android için TalkBack dinleyici uygulaması (gerçek okunan metin): isteğe bağlı iyileştirme.
5. Kendi WCAG hata listeni `config/wcag_katalog.yaml`'a gir, geçmiş denetimlerinle doğruluk ölç (Faz 5).

Aşağıdaki bölümler orijinal plandır; sıralama artık yukarıdaki listeye göredir.

---

## 0. Hedef tanımı (bitti sayılma kriteri)

> Kullanıcı panelde "Pegasus, iOS + Android, Uçuş arama akışı" seçip **Başlat** dediğinde sistem iki telefonda uygulamayı ekran okuyucuyla gezer. Hataları WCAG kataloğuna göre bulur, kullanıcının onayından sonra Drive'a **Başlık / Hata türü / WCAG / Not / Çözüm önerisi / Video** formatında yükler. Kesinlik ≥ %85, duyarlılık ≥ %80 olmalıdır.

---

## 1. Zaman çizelgesi

```
Hafta:            1    2    3    4    5    6    7    8    9    10
Faz 0  PoC        ████
Faz 1  Analiz+Drive    ████ ████
Faz 2  Android              ████ ████
Faz 3  iOS                            ████ ████
Faz 4  Ajan+Panel                               ████ ████
Faz 5  Kalibrasyon                                        ████ (sürekli)
```

| Faz | Süre | Çıktı | Kullanıcıya faydası |
|---|---|---|---|
| 0. Kavram kanıtı (PoC) | 1 hafta | Teknik risklerin yanıtı | Proje kararı netleşir |
| 1. Video analiz motoru + Drive | 2 hafta | Video yükle, bulgular Drive'a gitsin | **Hemen kullanılabilir**, manuel yazma işi biter |
| 2. Android otomasyonu | 2 hafta | TalkBack ile otomatik tarama | Android denetimi tamamen otomatik |
| 3. iOS otomasyonu | 2 hafta | VoiceOver ile otomatik tarama | iOS denetimi tamamen otomatik |
| 4. Ajan + Kontrol paneli | 2 hafta | Doğal dille senaryo, tek tık denetim | "Yarın Pegasus'a bak" senaryosu |
| 5. Kalibrasyon | Sürekli | Doğruluk metrikleri, istem iyileştirme | Güvenilirlik artar |

---

## 2. Faz 0: Kavram kanıtı (Hafta 1)

**Amaç:** Projeyi riske atan üç soruyu kod yazmaya başlamadan yanıtlamak.

| # | Görev | Kabul kriteri |
|---|---|---|
| 0.1 | Mac'e Appium 2, XCUITest ve UiAutomator2 sürücülerini kur. iPhone'da WebDriverAgent'ı imzala (Apple Developer hesabı gerekir). | `appium driver list` iki sürücüyü gösteriyor, Pegasus Appium ile açılıyor. |
| 0.2 | **iOS kritik test:** VoiceOver açıkken Appium ile sağa kaydırma gönder. Odak bir sonraki öğeye geçiyor mu? | Evet/Hayır + iOS sürümü not edilir. |
| 0.3 | Hayırsa ESP32 BLE klavye prototipi: `Ctrl+Option+→` gönder. | VoiceOver odağı klavye komutuyla ilerliyor. |
| 0.4 | iPhone ekran + VoiceOver sesini `ffmpeg -f avfoundation` ile Mac'te kaydet. | Ses ve görüntünün bulunduğu MP4. |
| 0.5 | Android: TalkBack aç/kapat (adb), `scrcpy --record` ile sesli kayıt. | TalkBack sesi duyulan MP4. |
| 0.6 | `ornekvideo2.mp4` → faster-whisper. "Back" sözcüğü `en` olarak etiketleniyor mu? | Dil tespiti doğru. |
| 0.7 | `ornekvideo3.mp4` → OpenCV ile odak çerçevesi koordinatlarını çıkar. | Kare bazında çerçeve konum listesi. |
| 0.8 | Google Cloud projesi aç, Drive + Sheets API etkinleştir, OAuth istemcisi oluştur. | Test klasörü ve Sheet API ile oluşturuldu. |

**Karar noktası (Hafta 1 sonu):** iOS için Seçenek A (Appium hareketi) mı, Seçenek B (BLE klavye) mi kullanılacak?

---

## 3. Faz 1: Video analiz motoru + Drive (Hafta 2–3)

**Amaç:** Bugün elle çektiğin videoları yüklediğinde bulguların otomatik çıkması ve Drive'a gitmesi.

### Görevler

| # | Görev | Ayrıntı |
|---|---|---|
| 1.1 | Proje iskeleti | `a11y-auditor/` repo, Python paket yapısı (aşağıda), `.env`, ayar dosyası |
| 1.2 | WCAG kataloğu | Senin hata türü listeni `config/wcag_katalog.yaml` olarak gir: ad, WCAG kodu, seviye, açıklama, varsayılan iOS/Android çözüm şablonu |
| 1.3 | Video ön işleme | ffmpeg ile ses ayırma, 2 fps kare çıkarma, sahne değişimi tespiti |
| 1.4 | Konuşma → metin | faster-whisper ile söz bazında zaman damgası ve dil. Türkçe ekran okuyucu terimleri sözlüğü: "düğme", "başlık", "seçili", "sekme" vb. |
| 1.5 | Odak takibi | OpenCV ile VoiceOver/TalkBack odak çerçevesi tespiti, her söz için odaklanan bölgenin koordinatı |
| 1.6 | Kural motoru v1 | (a) Dil kontrolü (3.1.2), (b) odak sırası atlaması (2.4.3), (c) anlamsız etiket ("button", "image", "icon_back") (4.1.2) |
| 1.7 | Claude analizcisi v1 | Kare + söz metni girdi olarak verilir → JSON bulgular. İlk hedef: başlık eksik (1.3.1), rol/durum eksik (4.1.2). Çıktı şeması aşağıda. |
| 1.8 | Birleştirme + tekilleştirme | Kural ve yapay zekâ bulgularını birleştir, aynı öğedeki tekrarları tek bulguda topla, önem derecesi ata |
| 1.9 | Klip kesme | Her bulgu için ±3 sn MP4, isteğe bağlı altyazı |
| 1.10 | Drive/Sheets yükleyici | Klasör yapısı, Sheet oluşturma/ekleme, video yükleme, linkleri hücreye yazma |
| 1.11 | Basit inceleme ekranı | Streamlit: bulgu kartları, Onayla/Düzenle/Reddet, Ekstra hata ekle, Drive'a yükle |
| 1.12 | Test | 3 örnek video: sistem 3 bilinen hatanın 3'ünü de bulmalı |

### Bulgu JSON şeması

```json
{
  "baslik": "Geri düğmesi İngilizce okunuyor",
  "hata_turu": "Dil Özelliği",
  "wcag": ["3.1.2"],
  "seviye": "AA",
  "not": "VoiceOver geri düğmesini 'Back' olarak seslendiriyor.",
  "cozum_onerisi": "accessibilityLabel = \"Geri\" atayın; tr yerelleştirmesini kontrol edin.",
  "platform": "iOS",
  "ekran": "Uçuş Seçimi",
  "onem": "Orta",
  "guven": 0.96,
  "kanit": { "baslangic_sn": 2.1, "bitis_sn": 3.4, "soylenen": "Back, button", "oge_bounds": [8, 52, 44, 44] },
  "kaynak": "otomatik"
}
```

### Kod yapısı

```
a11y-auditor/
├── config/
│   ├── wcag_katalog.yaml
│   ├── apps/pegasus.yaml          # bundle id, paket adı, dil, yasaklı eylemler
│   └── scenarios/pegasus_ucus_arama.md
├── auditor/
│   ├── capture/      ios.py android.py recorder.py
│   ├── driver/       appium_client.py voiceover.py talkback.py ble_keyboard.py
│   ├── analysis/     transcribe.py focus_tracker.py rules/*.py llm_judge.py merge.py
│   ├── report/       clips.py drive.py sheets.py
│   ├── agent/        agent.py tools.py
│   └── web/          app.py templates/
├── android-listener/  # Kotlin AccessibilityService (Faz 2)
├── firmware/          # ESP32 BLE klavye (Faz 0/3, gerekirse)
├── sessions/          # oturum paketleri
└── tests/fixtures/    ornekvideo1-3.mp4 + beklenen_bulgular.json
```

**Faz 1 kabul kriteri:** `ornekvideo1-3.mp4` panele yüklendiğinde 3 hata doğru WCAG koduyla bulunur ve tek tıkla Drive'da klasör, Sheet ve 3 klip oluşur.

---

## 4. Faz 2: Android otomasyonu (Hafta 4–5)

| # | Görev | Kabul kriteri |
|---|---|---|
| 2.1 | `android-listener` uygulaması: AccessibilityService, `TYPE_VIEW_ACCESSIBILITY_FOCUSED` ve `TYPE_ANNOUNCEMENT` olaylarını zaman damgasıyla logcat'e yazar | TalkBack gezinirken her odak bir log satırı |
| 2.2 | TalkBack sürücüsü: aç/kapat, sonraki/önceki öğe, etkinleştir | Ekran baştan sona otomatik taranıyor |
| 2.3 | Tarama algoritması: ilk öğeden başla, son öğeye ya da döngüye kadar ilerle, kaydırılabilir listelerde aşağı kaydır | Uzun listede tüm öğeler gezildi, döngü (odak tuzağı) tespit edildi |
| 2.4 | Her adımda ağaç (`getPageSource`) ve ekran görüntüsü kaydet | `steps.jsonl` eksiksiz |
| 2.5 | Ağaç tabanlı kurallar: dokunma hedefi 2.5.8, etiket-görünen metin uyumu 2.5.3, `heading` özelliği, `content-desc` boş | Kural testleri geçiyor |
| 2.6 | Kontrast kuralı (1.4.3), ekran görüntüsünden metin/arka plan piksel analizi | Bilinen düşük kontrastlı örnek yakalanıyor |
| 2.7 | Büyük yazı tipi testi: `adb shell settings put system font_scale 2.0` ile tekrar tara, kesilen metinleri Claude'a sor | 1.4.4 bulguları üretiliyor |
| 2.8 | Pegasus Android'de tam akış denemesi | 1 akış uçtan uca, insan müdahalesi olmadan |

---

## 5. Faz 3: iOS otomasyonu (Hafta 6–7)

| # | Görev | Kabul kriteri |
|---|---|---|
| 3.1 | VoiceOver sürücüsü (Faz 0 kararına göre Appium hareketi ya da BLE klavye) | Sonraki öğe / etkinleştir / rotor komutları çalışıyor |
| 3.2 | VoiceOver aç/kapat: Erişilebilirlik Kısayolu (yan tuşa 3 kez basma) ya da Ayarlar otomasyonu | Oturum başında/sonunda otomatik |
| 3.3 | Sesli kayıt servisi (avfoundation) oturumla senkron | Video ve adım zaman damgaları ±200 ms içinde |
| 3.4 | Odaklanan öğe eşleme: video odak çerçevesi ↔ XCUITest ağaç öğesi | Her söz bir ağaç öğesine bağlanıyor |
| 3.5 | Xcode Accessibility Audit sonuçlarını (varsa) ek kanıt olarak içe al | Ek bulgular kataloğa eşleniyor |
| 3.6 | Dynamic Type (en büyük boyut) ve yatay mod testleri | 1.4.4 ve 1.3.4 bulguları |
| 3.7 | Pegasus iOS tam akış | Örnek videolardaki 3 hata, **otomatik gezinmede de** bulunuyor |

---

## 6. Faz 4: Ajan + Kontrol paneli (Hafta 8–9)

| # | Görev | Ayrıntı |
|---|---|---|
| 4.1 | Ajan araçları | `screenshot`, `get_tree`, `tap(element)`, `type(text)`, `scroll`, `back`, `sweep_screen()` (tam ekran okuyucu taraması), `finish` |
| 4.2 | Ajan döngüsü | Claude (`claude-opus-5-5`) senaryoyu okur, her ekranda önce `sweep_screen`, sonra sonraki ekrana gezinir. Ziyaret edilen ekranlar kaydedilir, aynı ekran iki kez taranmaz. |
| 4.3 | Güvenlik kuralları | `apps/pegasus.yaml` içindeki `yasakli_eylemler` (ör. "Öde", "Satın Al", "Rezervasyonu Onayla") ajan aracında kod seviyesinde engellenir, istemle değil |
| 4.4 | Uygulama profilleri | Yeni uygulama eklemek = yeni bir YAML dosyası (bundle id, paket, dil, giriş bilgisi referansı, yasaklılar) |
| 4.5 | Panel v2 (FastAPI) | Yeni denetim formu, canlı ilerleme (hangi ekranda, kaç bulgu), inceleme ekranı, geçmiş denetimler, Drive linkleri |
| 4.6 | Paralel çalışma | iOS ve Android aynı anda |
| 4.7 | Bildirim | Analiz bitince e-posta ya da masaüstü bildirimi |
| 4.8 | Regresyon karşılaştırması | "Önceki Pegasus denetimine göre: 5 hata düzeltilmiş, 2 yeni hata" |

### Örnek senaryo dosyası: `config/scenarios/pegasus_ucus_arama.md`

```markdown
# Pegasus — Uçuş arama akışı
Uygulama: pegasus
Hedef: Uçuş arama → sonuçlar → uçuş seçimi → paket seçimi → yolcu bilgileri (DUR)

1. Ana sayfada "Gidiş-Dönüş" seç.
2. Nereden: İstanbul (SAW), Nereye: Tiran. Gidiş 24 Aralık, dönüş 30 Aralık. 1 yetişkin.
3. "Uçuş Ara"ya bas.
4. Gidiş uçuşları listesinde en ucuz uçuşu seç, SÜPER EKO paketini seç.
5. Dönüş uçuşlarında aynısını yap.
6. Yolcu bilgileri ekranına gelince DUR. Hiçbir form gönderme.

Her ekranda tam ekran okuyucu taraması yap. Takvim, fiyat listesi ve uçuş kartlarına özellikle dikkat et.
```

**Faz 4 kabul kriteri:** Kullanıcı panelden Pegasus'u seçip Başlat'a basar. Sistem müdahale olmadan iki platformu tarar, bulguları inceleme ekranına getirir, onaydan sonra Drive'a yükler.

---

## 7. Faz 5: Kalibrasyon ve doğruluk (Hafta 10 ve sonrası)

| # | Görev |
|---|---|
| 5.1 | Altın veri seti: Drive'daki geçmiş manuel denetimlerini (video + not) içe aktar, `beklenen_bulgular.json` formatına çevir |
| 5.2 | Değerlendirme betiği: `python -m auditor.eval` hata türü bazında kesinlik/duyarlılık raporu üretir |
| 5.3 | Reddedilen bulgulardan istem iyileştirme, kural eşiklerini ayarlama |
| 5.4 | Panelde doğruluk göstergesi: son 30 denetimde hata türü bazında metrikler |
| 5.5 | Her istem/kural değişikliğinden önce altın setle regresyon testi |

**Hedefler:** Kesinlik ≥ %85, duyarlılık ≥ %80. Denetim başına süre bugünkü manuel süreye göre en az %70 daha kısa.

---

## 8. Hemen yapılacaklar (bu hafta)

- [ ] **WCAG hata türü listeni** bir dosya olarak paylaş (Excel/Sheet/metin). `wcag_katalog.yaml`'ın temeli olacak.
- [ ] Drive'daki **mevcut bir denetim klasörünün** örneğini paylaş, formatı birebir taklit edeceğiz (Sheet mi, Doc mu, klasör adlandırma kuralı nedir?).
- [ ] Apple Developer hesabı var mı? (WebDriverAgent imzası için gerekli; ücretsiz hesap 7 günde bir yeniden imza ister, ücretli hesap 99 $/yıl.)
- [ ] Test cihazlarını belirle: iPhone modeli/iOS sürümü, Android modeli/sürümü.
- [ ] Pegasus için **test hesabı**, ve denetim izninin/sözleşmesinin kapsamı.
- [ ] Google Cloud projesi açma yetkisi (şirket hesabı mı, kişisel hesap mı?).
- [ ] Claude aboneliği (Pro/Max) ve Claude Code CLI bu Mac'te kurulu (✅ kurulu: 2.1.284). API anahtarı şimdilik gerekmiyor.

---

## 9. Riskler ve karar noktaları

| Ne zaman | Karar | Seçenekler |
|---|---|---|
| Hafta 1 sonu | iOS VoiceOver girdi yöntemi | A: Appium hareketi / B: BLE klavye / C: iOS yalnız manuel kayıt + otomatik analiz |
| Hafta 3 sonu | Faz 1 kullanılabilir mi? | Gerçek işte bir hafta kullan, geri bildirime göre Faz 2 önceliklerini güncelle |
| Hafta 5 sonu | Android doğruluğu yeterli mi? | Hedefin altındaysa Faz 5 kalibrasyonunu öne çek |
| Hafta 9 sonu | Ölçekleme | Birden fazla uygulama/cihaz çiftliği, ekip kullanımı, rapor şablonları |

---

## 10. Bütçe özeti

| Kalem | Tahmini |
|---|---|
| Apple Developer Programı | 99 $/yıl |
| ESP32 geliştirme kartı (gerekirse) | 5–10 $ |
| Claude Code CLI (mevcut Pro/Max aboneliği) | Ek ücret yok; abonelik limitleri geçerli. API'ye geçilirse akış başına ~1–3 $ |
| Google Cloud (Drive/Sheets API) | Ücretsiz kota yeterli |
| Whisper, Appium, OpenCV, ffmpeg, scrcpy | Açık kaynak, ücretsiz (Appium: Apache 2.0 lisanslı, OpenJS Foundation projesi) |
| Bulut cihaz çiftliği (BrowserStack, Sauce Labs vb.) | **Gerekmiyor.** Kendi telefonlarımızı kullanıyoruz. İleride çok sayıda cihaza ölçeklemek istenirse isteğe bağlı, aylık ~150–250 $ |
| Donanım | Mevcut Mac + 1 iPhone + 1 Android |
