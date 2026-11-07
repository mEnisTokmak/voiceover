# Mobil Erişilebilirlik Otomatik Denetim Sistemi — Teknik Rapor

**Konu:** iOS (VoiceOver) ve Android (TalkBack) uygulamalarında ekran okuyucu deneyimini WCAG 2.2'ye göre otomatik denetleyen ve bulguları Google Drive'a yükleyen sistem
**Hazırlanma tarihi:** 6 Kasım 2026
**Örnek uygulama:** Pegasus (iOS) — `ornekvideo1/2/3.mp4`

---

## 1. Özet

Bugün yaptığın iş şu: uygulamayı VoiceOver açıkken kullanıyorsun, ekranı kaydediyorsun, hatayı fark edip Drive'a **Başlık / Hata türü (WCAG) / Not / Çözüm önerisi** ve videoyla birlikte yüklüyorsun.

Hedeflenen sistem bu işi dört otomatik adıma bölüyor:

1. **Kullanma:** Bir ajan uygulamayı gerçek telefonda ekran okuyucu açıkken senin yerine gezer.
2. **Kayıt:** Her adımda görüntü, ekran okuyucunun söylediği ses ve erişilebilirlik ağacı (her öğenin etiketi, rolü, dili, konumu) kaydedilir.
3. **Analiz:** Kural motoru ve yapay zekâ (görüntü + metin) bu kayıtları WCAG kriterlerine göre değerlendirir, hata adaylarını çıkarır.
4. **Raporlama:** Sen bulguları bir panelde onaylar ya da düzeltirsin. Onaylananlar Drive'a senin bugünkü formatında yüklenir: Sheet satırı ve kırpılmış video klibi.

> **Önemli tasarım kararı (insan onayı):** Ekran okuyucu hatalarının bir kısmı yorum ister. Örneğin "bu metin görsel olarak başlık mı?" sorusu buna girer. Tamamen otomatik ve onaysız yükleme bir süre sonra yanlış bulgularla güven kaybettirir. Profesyonel denetim araçlarının çoğu bu yüzden "otomatik tespit, uzman onayı" modelini kullanıyor. Sistem senin işinin %80–90'ını üstlenir; son karar sende kalır. Senin onayların aynı zamanda sistemin doğruluğunu ölçmek için etiketli veri olur (Bölüm 9).

---

## 2. Örnek videoların analizi: sistem bu hataları nasıl yakalar?

| Video | Senin bulgun | WCAG kriteri | Otomatik tespit yöntemi |
|---|---|---|---|
| `ornekvideo3.mp4` (18 sn) | Odak sırası hatalı: uçuş bilgileri okunmadan tarih ve fiyat alanına geçiyor | **2.4.3 Odak Sırası (A)**, **1.3.2 Anlamlı Sıra (A)** | Her adımda odak çerçevesinin koordinatı kaydedilir. Odak, aynı kart içindeki öğeleri bitirmeden kart dışına ya da görsel okuma sırasına (yukarıdan aşağı, soldan sağa) aykırı bir yere atlarsa kural tetiklenir. Örnek: `İstanbul 12:00` okunmadan `24/12/2026` ve `4.037,00 TL` odaklanıyor. |
| `ornekvideo2.mp4` (9 sn) | Geri düğmesi İngilizce okunuyor ("Back") | **3.1.2 Parçaların Dili (AA)**, **3.1.1 Sayfanın Dili (A)** | Ses kaydı konuşma tanıma modeline (Whisper) verilir. Model hem metni hem **dili** döndürür. Beklenen dil `tr` iken `en` algılanan her söz hata adayıdır. Ek olarak erişilebilirlik ağacında `label="Back"` gibi İngilizce sabit metinler sözlükle yakalanır. |
| `ornekvideo1.mp4` (3,5 sn) | "Seçili uçuşlar" metni başlık olduğu hâlde "başlık" denmiyor | **1.3.1 Bilgi ve İlişkiler (A)**, **2.4.6 Başlıklar ve Etiketler (AA)** | Yapay zekâ ekran görüntüsünde görsel olarak başlık olan metinleri bulur (büyük/kalın, bölüm açan). Ardından iki kontrol yapılır: ağaçta `header` özelliği (trait) var mı, VoiceOver sözünde "başlık" ya da "heading" geçiyor mu? İkisi de yoksa hata adayı oluşur. |

Üç hata türü de **otomatik yakalanabilir** türden. Bunlar sistemin ilk sürümünde (MVP) test senaryosu olarak kullanılacak.

---

## 3. Sistem mimarisi

```
┌──────────────────────────────────────────────────────────────────────┐
│  KONTROL PANELİ (Web)  —  "Bugünkü iş: Pegasus iOS, Uçuş arama akışı" │
└───────────────┬──────────────────────────────────────────▲───────────┘
                │ görev                                     │ onay/düzeltme
┌───────────────▼───────────────┐              ┌────────────┴───────────┐
│ 1. AJAN / SÜRÜCÜ (Driver)     │              │ 4. İNCELEME + RAPOR    │
│ Claude Agent + Appium         │              │ Bulgu listesi, video   │
│ - Senaryoyu doğal dilden      │              │ klipleri, WCAG eşleme  │
│   adımlara çevirir            │              │ → Google Drive/Sheets  │
│ - Ekran okuyucuyla gezer      │              └────────────▲───────────┘
└───────────────┬───────────────┘                           │
                │                                           │
┌───────────────▼───────────────┐              ┌────────────┴───────────┐
│ 2. KAYIT (Capture)            │─────────────▶│ 3. ANALİZ              │
│ - Ekran videosu + ses         │  oturum      │ - Konuşma→metin + dil  │
│ - Her adımda a11y ağacı       │  paketi      │ - Kural motoru (WCAG)  │
│ - Odaklanan öğe + zaman damgası│             │ - Claude görsel analiz │
└───────────────────────────────┘              │ - Önem derecesi        │
                                               └────────────────────────┘
```

### 3.1 Katman 1: Ajan / Sürücü (uygulamayı kullanan taraf)

**Temel araç:** [ 2](https://appium.io), üzerinde iki sürücü var:
- iOS: `appium-xcuitest-driver` (WebDriverAgent ile gerçek iPhone'u kontrol eder)
- Android: `appium-uiautomator2-driver`

**Akıllı katman:** Claude (Agent SDK ya da API ile tool-use). Ajana Appium komutları araç olarak verilir: `ekran_görüntüsü_al`, `ağacı_oku`, `dokun`, `kaydır`, `sonraki_öğeye_git`. Böylece senaryoyu doğal dille yazabilirsin:

> "Pegasus'u aç, İstanbul–Tiran 24 Aralık gidiş, 30 Aralık dönüş uçuşu ara, en ucuz uçuşu seç, ödeme ekranına kadar ilerle. **Ödeme yapma.** Her ekranda ekran okuyucuyla tüm öğeleri baştan sona gez."

Ajan her ekranda iki iş yapar:
- **Gezinme (navigation):** Bir sonraki ekrana geçmek için normal dokunma.
- **Tarama (sweep):** Ekran okuyucuyla ilk öğeden son öğeye "sağa kaydır" hareketiyle tek tek geçer. Kör bir kullanıcının deneyimi bu adımda kaydedilir.

**Ekran okuyucu hareketlerini otomatikleştirme (projenin en kritik teknik riski):**

| Platform | Yöntem | Not |
|---|---|---|
| Android / TalkBack | `adb shell settings put secure enabled_accessibility_services ...` ile TalkBack'i aç/kapat. Gezinme için ya UiAutomator `ACTION_ACCESSIBILITY_FOCUS` ile öğe öğe odak ya da TalkBack klavye kısayolları (`Alt + →`) | Sorunsuz otomatikleştirilebilir. Ayrıca kendi yazacağımız küçük bir **AccessibilityService "dinleyici" uygulaması**, TalkBack'in odakladığı her öğeyi ve duyuruyu (announcement) metin olarak loglar. Bu, ses tanımadan daha kesin sonuç verir. |
| iOS / VoiceOver | **Seçenek A:** Appium ile VoiceOver açıkken sentetik kaydırma hareketi. **Seçenek B (önerilen yedek):** iPhone'a Bluetooth klavye gibi bağlanan küçük bir donanım (ESP32, ~5 $). VoiceOver klavye komutlarını gönderir: `Ctrl+Option+→` sonraki öğe, `Ctrl+Option+Space` etkinleştir. Mac'teki yazılım bu cihazı USB/seri port üzerinden yönetir. | Apple, VoiceOver'ın ne söylediğini veren bir API sunmuyor ve sentetik hareketlerin VoiceOver'a ulaşıp ulaşmadığı iOS sürümüne göre değişebilir. Bu yüzden **Faz 0'da iki seçenek de denenecek.** Seçenek B, gerçek kullanıcı girdisi olduğu için her iOS sürümünde çalışır ve profesyonel test laboratuvarlarında kullanılan bir yöntemdir. |

> iOS Simülatöründe VoiceOver yok. Gerçek iPhone şart. Android'de emülatör + TalkBack çalışır, ama nihai doğrulama gerçek cihazda yapılmalı.

### 3.2 Katman 2: Kayıt

Her oturum bir **oturum paketi** üretir:

```
sessions/2026-11-07_pegasus_ios_8.3.1/
├── recording.mp4           # ekran + ekran okuyucu sesi
├── steps.jsonl             # her adım: zaman, ekran, odaklanan öğe, ağaç dosyası
├── trees/step_0042.xml     # o anki erişilebilirlik ağacı
├── frames/step_0042.png    # o anki ekran görüntüsü
└── meta.json               # cihaz, OS, uygulama sürümü, dil, senaryo
```

**Ses dahil ekran kaydı:**
- **iOS:** iPhone kabloyla Mac'e bağlanır. macOS iPhone ekranını ve sesini bir AVFoundation kaynağı olarak gösterir (QuickTime'daki "Yeni Film Kaydı → iPhone" ile aynı mekanizma). `ffmpeg -f avfoundation` ile görüntü ve VoiceOver sesi birlikte kaydedilir. Appium'un kendi kayıt özelliği ses almaz, bu yüzden bu yöntem gerekiyor.
- **Android:** [`scrcpy`](https://github.com/Genymobile/scrcpy) 2.x, Android 11+ cihazlarda görüntü ve sesi birlikte kaydeder (`scrcpy --record oturum.mp4`).

**Erişilebilirlik ağacı:** Appium `getPageSource()` iOS'ta XCUITest öğelerini (etiket, değer, tür, konum, görünürlük) ve Android'de `content-desc`, `text`, `class`, `bounds`, `focusable`, `heading` bilgilerini verir.

### 3.3 Katman 3: Analiz

Analiz üç kaynaktan gelen kanıtı birleştirir:

1. **Ne söylendi?** Ses → `faster-whisper` (yerel, ücretsiz). Çıktı: zaman damgalı metin ve **dil etiketi**. Android'de buna dinleyici uygulamasının logu eklenir.
2. **Ne odaklandı?** Videodaki VoiceOver/TalkBack odak çerçevesi (OpenCV ile siyah dikdörtgen tespiti) ve ağaçtaki öğe koordinatı.
3. **Ekranda ne görünüyor?** Ekran görüntüsü → Claude (görsel model): başlıklar, düğmeler, ikonlar, kartlar, okuma sırası.

Bu kanıtlar iki motora gider:

- **Kural motoru (deterministik, hızlı, kesin):** Ölçülebilir kurallar burada çalışır. Örnekler: odak sırası atlaması, İngilizce sözcük, etiketsiz düğme, 24×24 pt altı dokunma hedefi, kontrast oranı, aynı etiketin tekrarı.
- **Yapay zekâ değerlendirici (yorum gerektiren durumlar):** Claude'a ekran görüntüsü, ağaç ve söylenen metin birlikte verilir. Şu tür sorular sorulur: "Görsel olarak başlık olan ama başlık olarak duyurulmayan bir öğe var mı?", "Etiket öğenin işlevini anlatıyor mu (`düğme` yerine `Uçuşu düzenle, düğme`)?", "Okuma sırası mantıklı mı?" Çıktı yapılandırılmış JSON'dur: başlık, hata türü, WCAG kodu, not, çözüm önerisi, güven skoru, kanıt zaman aralığı.

Her bulgu için `ffmpeg` hatanın **±3 saniyelik** video klibini keser ve isteğe bağlı olarak söylenen metni altyazı olarak ekler.

### 3.4 Katman 4: İnceleme ve Drive'a yükleme

**İnceleme paneli** (basit bir web arayüzü):
- Bulgular kartlar hâlinde listelenir: video klibi, ekran görüntüsünde işaretli öğe, söylenen metin.
- Her kartta **Onayla / Düzenle / Reddet** seçenekleri var. Reddedilenler "yanlış pozitif" olarak saklanır ve sistemin kalibrasyonunda kullanılır.
- **"Ekstra hata ekle"** butonu: sistemin kaçırdığı hatayı sen eklersin. Bunlar da "kaçırılan" (false negative) olarak işaretlenir.

**Drive çıktısı (bugünkü formatının otomatik hâli):**

```
Drive/Erişilebilirlik Denetimleri/
└── Pegasus/
    └── 2026-11-07_iOS_v8.3.1/
        ├── Bulgular  (Google Sheet)
        ├── Rapor.pdf (özet rapor, isteğe bağlı)
        └── Videolar/
            ├── 001_odak-sirasi_donus-ucuslari.mp4
            ├── 002_dil-ozelligi_geri-dugmesi.mp4
            └── 003_baslik-eksik_secili-ucuslar.mp4
```

**`Bulgular` Sheet sütunları:**

| # | Başlık | Hata Türü | WCAG Kriteri | Seviye | Not | Çözüm Önerisi | Platform | Ekran | Önem | Video | Kaynak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Dönüş uçuşları ekranında odak sırası hatalı | Odak Sırası | 2.4.3 | A | VoiceOver uçuş saat/şehir bilgilerini okumadan tarih ve fiyat alanına geçiyor. | Kart içeriğini tek bir erişilebilirlik öğesi olarak gruplayın (`accessibilityElements` sırası / `shouldGroupAccessibilityChildren`). Android'de `screenReaderFocusable` ve `accessibilityTraversalAfter` kullanın. | iOS | Dönüş Uçuşları | Yüksek | [link] | Otomatik |
| 2 | Geri düğmesi İngilizce okunuyor | Dil Özelliği | 3.1.2 | AA | "Back" olarak okunuyor. | `accessibilityLabel = "Geri"` atayın, uygulama yerelleştirmesini (tr.lproj) kontrol edin, `accessibilityLanguage` değerini doğru ayarlayın. | iOS | Uçuş Seçimi | Orta | [link] | Otomatik |
| 3 | "Seçili uçuşlar" başlık olarak duyurulmuyor | Başlık Eksik | 1.3.1 / 2.4.6 | A | Görsel olarak bölüm başlığı, ancak VoiceOver "başlık" demiyor. Rotor ile başlıklar arasında gezilemiyor. | iOS: `.accessibilityAddTraits(.isHeader)`. Android: `ViewCompat.setAccessibilityHeading(view, true)` / Compose `Modifier.semantics { heading() }`. | iOS | Özet | Orta | [link] | Otomatik |
| 4 | … | | | | | | | | | | Manuel (Ekstra) |

"Ekstra hatalar ve notlar" ayrı bir sekmede tutulur (`Ekstra` sekmesi). Ya da aynı tabloda `Kaynak = Manuel` olarak işaretlenir.

**Teknik yol:** Google Drive API v3 ve Sheets API v4, OAuth ile senin hesabın üzerinden. Yüklenen her video için paylaşım linki alınır ve Sheet hücresine yazılır.

---

## 4. WCAG hata türü kataloğu (sistemin kontrol edeceği kurallar)

Kendi WCAG hata listen sisteme **`wcag_katalog.yaml`** olarak yüklenecek. Sistem bulguları bu katalogdaki adlarla eşler, böylece Drive'daki "Hata türü" sütunu senin terminolojinle aynı kalır. Önerilen başlangıç kapsamı:

| Hata türü | WCAG | Seviye | Otomasyon düzeyi | Tespit yöntemi |
|---|---|---|---|---|
| Etiketsiz / anlamsız düğme ("düğme", "image", dosya adı) | 1.1.1, 4.1.2 | A | 🟢 Tam | Ağaç + söz |
| Rol eksik/yanlış (düğme "düğme" denmiyor) | 4.1.2 | A | 🟢 Tam | Ağaç trait/class |
| Durum/değer okunmuyor (seçili, açık/kapalı) | 4.1.2 | A | 🟡 Yarı | Ağaç + Claude |
| Başlık olarak işaretlenmemiş başlık | 1.3.1, 2.4.6 | A/AA | 🟡 Yarı | Claude görsel + ağaç |
| Odak sırası hatalı | 2.4.3, 1.3.2 | A | 🟢 Tam | Odak koordinat dizisi |
| Dekoratif öğe odak alıyor / gereksiz duraklar | 1.1.1, 1.3.1 | A | 🟡 Yarı | Ağaç + Claude |
| Parçaların dili yanlış (İngilizce okuma) | 3.1.2 | AA | 🟢 Tam | Whisper dil tespiti |
| Görünen metin ile etiket uyumsuz | 2.5.3 | A | 🟢 Tam | Görünen metin ve etiket karşılaştırması |
| Odak tuzağı / ekrana erişilemeyen öğe | 2.1.2, 2.1.1 | A | 🟢 Tam | Tarama döngü tespiti |
| Durum mesajı duyurulmuyor (hata, yükleniyor, sepete eklendi) | 4.1.3 | AA | 🟡 Yarı | Ekran değişimi var ama söz yok |
| Modal açılınca odak arkada kalıyor | 2.4.3 | A | 🟢 Tam | Ekran değişimi ve odak konumu |
| Form alanı etiketi / hata mesajı ilişkilendirilmemiş | 3.3.1, 3.3.2 | A | 🟡 Yarı | Ağaç + Claude |
| Dokunma hedefi < 24×24 pt | 2.5.8 | AA | 🟢 Tam | Ağaç bounds |
| Metin kontrastı < 4.5:1 | 1.4.3 | AA | 🟢 Tam | Piksel analizi |
| Büyük yazı tipinde (Dynamic Type / Font Scale) metin kesiliyor | 1.4.4 | AA | 🟡 Yarı | %200 yazı tipiyle tekrar tarama + Claude |
| Yatay/dikey yön kilidi | 1.3.4 | AA | 🟢 Tam | Döndürme testi |
| Zaman aşımı uyarısı yok | 2.2.1 | A | 🔴 Manuel | — |

🟢 Kural motoru güvenilir biçimde yakalar. 🟡 Claude aday üretir, insan onayı önemli. 🔴 Şimdilik manuel kalır.

---

## 5. Günlük kullanım: "Yarın Pegasus'u analiz edeceğim"

**Hazırlık (bir kez):** iPhone ve Android telefon Mac'e bağlı. Pegasus iki telefonda da yüklü, test hesabıyla giriş yapılmış.

**Sabah:**

1. Panelde **Yeni Denetim** butonuna basarsın.
   - Uygulama: `Pegasus` (kayıtlı profil: paket adı, bundle id, dil `tr`)
   - Platform: `iOS` ☑ `Android` ☑
   - Senaryo: hazır listeden `Uçuş arama → seçim → yolcu bilgisi` ya da serbest metin
   - Ek testler: ☑ Büyük yazı tipi ☑ Yatay mod
2. **Başlat.** Ajan iki telefonda senaryoyu çalıştırır ve her ekranda ekran okuyucuyla tam tarama yapar. Bir akış yaklaşık 10–20 dakika sürer. Bu sırada başka işle ilgilenebilirsin.
3. Analiz biter, panel bildirim gönderir: *"Pegasus iOS: 14 aday bulgu (9 yüksek güven), Android: 11 aday bulgu."*
4. **İnceleme (20–30 dk):** Kartları gezersin, videoyu izlersin, onaylar, düzeltir ya da reddedersin. Fark ettiğin ek hataları **Ekstra hata ekle** ile girersin.
5. **Drive'a yükle.** Klasör, Sheet ve video klipleri senin formatında oluşturulur. Link panoya kopyalanır.

**Yedek mod (otomatik gezinmenin zorlandığı ekranlar için):** Telefonu kendin kullanıp ekran kaydını panele **sürükle-bırak** yaparsın. Sistem yine analiz eder ve Drive'a yükler. Bu mod, `ornekvideo1-3` gibi elindeki mevcut kayıtlarla **ilk haftadan itibaren** çalışır.

---

## 6. Teknoloji yığını

| İş | Araç | Neden |
|---|---|---|
| Ana dil | Python 3.12 | Appium, Whisper, OpenCV, Google API'leri için en olgun ekosistem |
| Cihaz kontrolü | Appium 2 + XCUITest / UiAutomator2 | Endüstri standardı, iOS + Android tek API |
| iOS VoiceOver girdisi (yedek) | ESP32 BLE HID klavye | VoiceOver klavye komutları, iOS sürümünden bağımsız |
| Android ekran okuyucu logu | Kendi AccessibilityService uygulamamız (Kotlin, ~200 satır) | TalkBack odak/duyuru metni kesin olarak alınır |
| Ekran + ses kaydı | ffmpeg (avfoundation) / scrcpy | Ses dahil kayıt |
| Konuşma tanıma + dil | faster-whisper (large-v3) | Yerel, Türkçe başarılı, dil tespiti var |
| Görüntü işleme | OpenCV | Odak çerçevesi tespiti, kontrast |
| Yapay zekâ | **Claude Code CLI** (`claude -p`, Pro/Max aboneliği ile). Ölçeklenince Claude API'ye geçilebilir. | Ek API ücreti yok. Görselleri okur, `--json-schema` ile yapılandırılmış JSON verir, telefonu MCP üzerinden kullanabilir. |
| Panel | FastAPI + basit HTML/HTMX (ya da Streamlit ile hızlı başlangıç) | Hafif, tek kişilik kullanım için yeterli |
| Veri | SQLite + dosya sistemi | Kurulumsuz |
| Raporlama | Google Drive API v3, Sheets API v4 | Mevcut iş akışınla aynı |

**Donanım:** Mac (Apple Silicon), en az 1 iPhone (iOS 17+), en az 1 Android (11+), USB kablolar, isteğe bağlı ESP32 kartı.

**Tahmini işletme maliyeti:** Claude Code CLI aboneliğe dahil olduğu için ek ücret yok; tek sınır aboneliğin kullanım limitleri. API'ye geçilirse bir uygulama akışı (~30 ekran) yaklaşık 1–3 $. Whisper yerelde çalıştığı için ücretsiz.

### 6.1 Analizin Claude Code CLI ile yapılması

Analiz betiği her ekran için Claude'u komut satırından çağırır:

```bash
claude -p "Bu ekran görüntüsünü ve VoiceOver dökümünü WCAG kataloğuna göre değerlendir:
  frames/step_0042.png, steps/step_0042.json, config/wcag_katalog.yaml" \
  --output-format json \
  --json-schema "$(cat config/bulgu_semasi.json)" \
  --allowedTools "Read" \
  --model sonnet
```

- **Analiz (Faz 1):** Python, `subprocess` ile `claude -p` çağırır ve dönen JSON'u bulgu listesine ekler. Claude görselleri `Read` aracıyla açar.
- **Ajan (Faz 4):** Ayrıca bir ajan döngüsü yazmaya gerek kalmayabilir. Claude Code'a bir Appium/mobil MCP sunucusu `--mcp-config` ile bağlanır, senaryo dosyası istem olarak verilir. Claude telefonu kendisi kullanır.
- **Sınırlar:** Her çağrı birkaç saniyelik açılış süresi ekler. Abonelik limitleri (5 saatlik pencereler ve haftalık limit) uzun denetimlerde dolabilir. Bu yüzden her ekran ayrı çağrı yerine 5–10 ekran tek çağrıda gönderilir.
- **Kullanım koşulu:** Abonelik, kendi kişisel/iş kullanımın içindir. Sistem bir ürüne dönüşüp başkalarına sunulacaksa ya da ekipçe ölçeklenecekse Claude API anahtarına geçilmeli. Kod tarafında yalnızca çağrı katmanı değişir.

---

## 7. Riskler ve önlemler

| Risk | Etki | Önlem |
|---|---|---|
| iOS'ta VoiceOver hareketleri otomasyonla gönderilemiyor | Yüksek | Faz 0'da test edilecek. Yedek: BLE klavye donanımı. İkinci yedek: manuel kayıt + otomatik analiz modu. |
| Yapay zekâ yanlış bulgu üretir (yanlış pozitif) | Orta | İnsan onayı zorunlu. Güven skoru eşiği. Reddedilen bulgularla istem (prompt) iyileştirme. |
| Ajan canlı uygulamada istenmeyen işlem yapar (rezervasyon/ödeme) | Yüksek | Senaryolarda "yasaklı eylemler" listesi (Öde, Satın al, Onayla). Ödeme ekranında otomatik durma. Test hesabı. |
| Uygulama güncellemesi akışı bozar | Düşük | Ajan sabit koordinat yerine ekranı görerek karar verir. Senaryolar doğal dilde yazılır. |
| Whisper kısa sözcüklerde dil tespitinde hata yapar | Orta | Dil kontrolü yalnız ≥2 sözcüklü sözlerde yapılır. Ek olarak ağaçtaki etiket sözlük kontrolüyle doğrulanır. |
| Telefonda kişisel/yolcu verisi Drive'a gider | Orta | Test hesabı. İsteğe bağlı bulanıklaştırma. Drive klasör izinleri kısıtlı. |
| Üçüncü taraf uygulamayı test etme izni | — | Denetim, uygulama sahibinin yetkisi/sözleşmesi kapsamında yapılmalı. |

---

## 8. Neden bu yaklaşım? (Alternatiflerle karşılaştırma)

| Yaklaşım | Artı | Eksi |
|---|---|---|
| **Yalnız statik tarayıcılar** (Xcode Accessibility Inspector Audit, Google Accessibility Scanner, `performAccessibilityAudit()`) | Ücretsiz, hızlı | Odak sırası, dil, gerçek VoiceOver deneyimi gibi senin örnek hatalarını **yakalamaz**. Yalnızca ek kural kaynağı olarak kullanılacak. |
| **Ticari platformlar** (Deque axe DevTools Mobile, Evinced, BrowserStack App Accessibility) | Olgun | Pahalı. Drive formatına uymaz. Ekran okuyucu sesini analiz etmez. Uygulama kaynak koduna erişim gerekebilir (SDK entegrasyonu). |
| **Önerilen: ekran okuyucu + ses + ağaç + yapay zekâ + insan onayı** | Senin iş akışının birebir otomasyonu. Kaynak kod gerekmez, her mağaza uygulamasında çalışır. | Kurulum emeği. iOS otomasyonunda teknik risk (Faz 0'da çözülecek). |

---

## 9. Doğruluk nasıl ölçülecek?

Sistemin kendisi de ölçülebilir olmalı. Her denetimde panel şu metrikleri tutar:

- **Kesinlik (Precision):** Onaylanan bulgu / sistemin ürettiği bulgu. Hedef ≥ %85.
- **Duyarlılık (Recall):** Sistemin bulduğu / (sistemin bulduğu + senin "ekstra" eklediğin). Hedef ≥ %80.
- **Hata türü bazında** iki metrik ayrı ayrı (ör. "Dil özelliği: %97 kesinlik, Başlık eksik: %72").
- **Zaman kazancı:** Denetim başına harcanan dakika (bugünkü manuel süreyle kıyas).

**Altın veri seti:** Senin geçmiş manuel denetimlerin (Drive'daki videolar + notlar) sisteme verilir. Sistem bunları yeniden analiz eder ve senin bulgularınla karşılaştırılır. Böylece sistem canlıya çıkmadan önce doğruluğu bilinmiş olur.

---

## 10. Sonuç ve öneri

1. **Önce mevcut videolarınla çalışan analiz motorunu kur** (Faz 1). İlk haftadan itibaren değer üretir: kaydını yüklersin, bulgular ve Drive çıktısı otomatik oluşur.
2. **Sonra Android otomasyonu** (Faz 2): teknik olarak en kolay platform.
3. **Paralelde iOS VoiceOver otomasyonunu doğrula** (Faz 0 PoC), ardından üretime al (Faz 3).
4. **En son doğal dille senaryo yazan ajan ve panel** (Faz 4).

Ayrıntılı iş planı, süreler ve kabul kriterleri için: **[PLANLAMA.md](PLANLAMA.md)**

---

## 11. Uygulama sonrası notlar (7 Kasım 2026)

Sistem kuruldu (kurulum ve kullanım: **[README.md](README.md)**). Örnek videolarla yapılan ilk denemelerde, plandaki bazı varsayımlar şöyle düzeltildi:

- **Dil hatası sesin dilinden değil, sözcüğün kendisinden anlaşılıyor.** VoiceOver, İngilizce "Back arrow" etiketini Türkçe sesle okuyor. Konuşma tanıma bunu "bekeroğu" diye yazıyor ve ses dili tahmini kısa sözlerde güvenilmez çıktı ("Düzenle" sözü Fransızca sanıldı). Bu yüzden:
  - Kural motoru İngilizce sözlük ve ayarlanabilir **fonetik kalıplar** kullanıyor (`checks.yaml → fonetik_kaliplar`).
  - Yapay zekâ, transkripti odaklanan öğenin görüntüsüyle birlikte yorumluyor.
  - Yalnız ses dili tahminiyle raporlama varsayılan olarak kapalı.
- **Başlık ve odak sırası hataları yapay zekâ gerektiriyor.** Kural motoru tek başına (`LLM_BACKEND=none`) yalnız video 2'deki dil hatasını buldu. Claude ile birlikte 3 hatanın 3'ü de bulundu. Başlık ve odak sırası bulgularının güven skoru düşük (%40–55); bu, insan onayı adımının gerekli olduğunu doğruluyor.
- **Sistem senin listende olmayan aday bulgular da üretiyor.** Örnekler: "Icon Edit" ve "Free Refund 24" İngilizce okunuyor, Düzenle simgesi ayrı odak alıyor. Bunların hangisinin gerçekten hata olduğuna senin kararın ve gerekçen öğrenme verisine dönüşüyor.
- **Öğrenme, model eğitimi gerektirmeden çalışıyor.** Düzeltmeler ve gerekçeler sonraki analizlerde talimata ekleniyor. Test: gerekçeyle reddedilen bir bulgu, yeniden analizde tekrar üretilmedi.
