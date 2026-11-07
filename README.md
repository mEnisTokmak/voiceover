# Mobil Ekran Okuyucu Erişilebilirlik Denetimi

iOS (VoiceOver) ve Android (TalkBack) uygulamalarını WCAG 2.2'ye göre denetler. Bulguları bir panelde incelemen için hazırlar, onayladıklarını Google Drive'a yükler. Düzeltmelerinden öğrenir.

- **Ajan modu:** Yapay zekâ ajanı uygulamayı gerçek telefonda senaryoya göre gezer ve her ekranı ekran okuyucu gözüyle tarar.
- **Video modu:** Ekran okuyucu açıkken çektiğin sesli ekran kaydını yüklersin, sistem analiz eder.
- **Yapay zekâ arka ucu:** `cli` (Claude aboneliği), `api` (Claude API anahtarı) ya da `none` (yalnız kural motoru). `.env` dosyasından seçilir.

Rapor ve plan için: [RAPOR.md](RAPOR.md), [PLANLAMA.md](PLANLAMA.md)

---

## Mimari

```
┌──────────── Docker (her bilgisayarda aynı) ────────────┐        ┌──── Bilgisayarın kendisi ────┐
│ Panel (localhost:8000) · Analiz (ffmpeg + whisper)       │  HTTP  │ Appium (telefon köprüsü)     │──USB── iPhone / Android
│ Kural motoru · Claude (CLI/API) · Öğrenme · Drive        │ ─────▶ │ :4723                        │
└──────────────────────────────────────────────────────────┘        └──────────────────────────────┘
```

Telefon köprüsü Docker dışında çalışır. iPhone otomasyonu Apple'ın Xcode araçlarını gerektirir ve bunlar Docker içinde çalışmaz. **Video modu** için köprü gerekmez: yalnızca Docker yeterli.

| Bilgisayar | Video modu | Android ajanı | iOS ajanı |
|---|---|---|---|
| Mac | ✅ | ✅ | ✅ |
| Windows / Linux | ✅ | ✅ (Appium + adb kurulu olmalı) | ❌ (Apple kısıtı) |

---

## Kurulum

### 1. Docker kısmı (herkes)

```bash
git clone <repo> && cd voiceover
cp .env.example .env
```

`.env` içinde yapay zekâ arka ucunu seç:

| Seçenek | Ne gerekir | Ücret |
|---|---|---|
| `LLM_BACKEND=cli` | Claude Pro/Max aboneliği. Kendi bilgisayarında `claude setup-token` çalıştır, çıkan değeri `CLAUDE_CODE_OAUTH_TOKEN=` satırına yapıştır. | Aboneliğe dahil (abonelik limitleri geçerli) |
| `LLM_BACKEND=api` | `ANTHROPIC_API_KEY=` (console.anthropic.com) | Kullanım başına |
| `LLM_BACKEND=none` | Hiçbir şey | Ücretsiz; yalnız kural motoru (başlık, odak sırası gibi yorum gerektiren kontroller çalışmaz) |

```bash
docker compose up -d --build
```

Panel: **http://localhost:8000**

İlk analizde konuşma tanıma modeli (~500 MB) indirilir ve `data/models` klasörüne kaydedilir. Sonraki analizlerde yeniden indirilmez.

### 2. Telefon köprüsü (yalnız ajan modu için)

Mac'te bir kez:

```bash
./host/mac-kurulum.sh     # Appium, iOS/Android sürücüleri, adb
./host/kopru-baslat.sh    # her çalışma öncesi; terminal açık kalmalı
```

- **iPhone:** Xcode kurulu olmalı. Telefonda *Geliştirici Modu* açık olmalı. WebDriverAgent bir kez imzalanmalı; ayrıntılar betiğin çıktısında.
- **Android:** *USB hata ayıklama* açık olmalı, telefon `adb devices` çıktısında görünmeli.
- Uygulamanın paket/bundle adını [config/apps/pegasus.yaml](config/apps/pegasus.yaml) içinde doğrula. Yer tutucuları gerçek değerlerle değiştir.

### 3. Google Drive (bir kez)

1. Google Cloud Console'da bir proje aç. **Drive API** ve **Sheets API**'yi etkinleştir.
2. *OAuth istemci kimliği → Masaüstü uygulaması* oluştur. JSON'u `data/secrets/client_secret.json` olarak kaydet.
3. Yetkilendir:
   ```bash
   docker compose run --rm -p 8765:8765 auditor python -m auditor drive-yetki
   ```
   Çıkan bağlantıyı tarayıcıda aç ve izin ver. Token `data/secrets/token.json`'a yazılır.

---

## Günlük kullanım

1. `./host/kopru-baslat.sh` (ajan modu için) → http://localhost:8000
2. **Ajanı telefonda gezdir:** Uygulamayı, platformu ve senaryoyu seç (ya da serbest metin yaz), **Başlat**'a bas.
   **Ya da ekran kaydı yükle:** Sesli videoyu seç, **Yükle ve analiz et**'e bas.
3. Denetim sayfasında her bulgu için video klibi, duyulan metin, not ve çözüm önerisi gösterilir:
   - **✓ Onayla**
   - **✗ Reddet:** Nedenini yazarsan sistem bunu öğrenir ve benzerini bir daha raporlamaz.
   - **Düzenle ve onayla:** Hata türünü, başlığı veya notu düzelt. İstersen "Sisteme öğret" kutusuna kural yaz.
   - **➕ Ekstra hata ekle:** Sistemin kaçırdığı hatayı gir. Videodaki saniyeyi yazarsan klip otomatik kesilir.
4. **Onaylananları Drive'a yükle.** Şu yapı oluşur:
   `Erişilebilirlik Denetimleri/Pegasus/<tarih>_<platform>_<no>/` → `Bulgular` Sheet'i (Bulgular + Ekstra sekmeleri) ve `Videolar/` klasörü.
   Sheet sütunları: # · Başlık · Hata Türü · WCAG Kriteri · Seviye · Not · Çözüm Önerisi · Platform · Ekran · Önem · Video · Kaynak

---

## Akışı değiştirme (kod gerekmez)

Hepsi panelde **Kontroller ve Ayarlar** sayfasından ya da `config/` klasöründen düzenlenir. Değişiklik bir sonraki analizde geçerli olur; yeniden başlatma gerekmez.

| Dosya | Ne değişir |
|---|---|
| [config/checks.yaml](config/checks.yaml) | **Neye bakılacağı.** Kontrol aç/kapat, parametre değiştir. **Yeni kontrol:** `tur: llm` ve bir `talimat` yazman yeterli. |
| [config/wcag_katalog.yaml](config/wcag_katalog.yaml) | **Hata türleri** (Drive'daki "Hata Türü" sütunu): ad, WCAG kodu, seviye, varsayılan iOS/Android çözümü. Kendi listeni buraya koy. |
| [config/prompts/analiz.md](config/prompts/analiz.md) | Yapay zekâ denetçisinin talimatı |
| [config/prompts/ajan.md](config/prompts/ajan.md) | Telefonu gezen ajanın talimatı |
| [config/apps/*.yaml](config/apps/) | Uygulama profilleri. Yeni uygulama = yeni dosya. Paket adları ve **yasaklı eylemler** (ödeme vb.) burada; yasaklı eylemler kod seviyesinde engellenir. |
| [config/scenarios/*.md](config/scenarios/) | Ajan senaryoları (doğal dille) |
| [config/settings.yaml](config/settings.yaml) | Model, whisper boyutu, klip süresi, Drive klasörü |

Yeni bir *ölçülebilir* kural gerekiyorsa [auditor/analysis/rules.py](auditor/analysis/rules.py) içine `@rule("ad")` ile bir fonksiyon eklenir ve checks.yaml'da `kural: ad` olarak kullanılır.

## Öğrenme nasıl çalışır?

Model yeniden eğitilmez. Her geri bildirim kaydedilir ve sonraki analizlerde yapay zekâya talimat olarak verilir:

- **Düzeltme** (örneğin hata türü yanlış girilmiş): "Sistem X dedi, denetçi Y olarak düzeltti" örneği olarak saklanır. Hata türü değiştiyse kalıcı bir kural da otomatik üretilir.
- **Red ve gerekçe:** "Hata DEĞİL: …" kuralı oluşur.
- **Ekstra hata:** "Sistem kaçırdı, benzerini ara" örneği olarak saklanır.
- **Öğrenme ve Doğruluk** sayfası: kuralları gör, düzenle, kapat/aç, elle kural ekle. Hata türü bazında kesinlik ve duyarlılık tablosu da burada.
- **Yeniden analiz et** butonu, aynı videoyu güncel kurallarla tekrar değerlendirir. Daha önce karar verdiğin bulgular tekrar önerilmez.

Yapay zekânın her analizde gördüğü tam talimat `data/sessions/<denetim>/son_istem.md` dosyasına yazılır. Neyi neden yaptığını buradan kontrol edebilirsin.

---

## Komut satırı

```bash
docker compose run --rm -v "$PWD/tests:/tests" auditor python -m auditor analiz /tests/fixtures/ornekvideo2.mp4 --app pegasus --platform ios
docker compose run --rm auditor python -m auditor yeniden <denetim_id>
docker compose run --rm auditor python -m auditor ajan --app pegasus --platform android --senaryo pegasus_ucus_arama
docker compose run --rm auditor python -m auditor drive <denetim_id>
docker compose run --rm -v "$PWD/tests:/tests" auditor python -m unittest discover -s /tests -v
```

## Bilinen sınırlar

- **Ajanın tarama sırası yaklaşıktır.** Ajan modunda okuma sırası, erişilebilirlik ağacının sırasından çıkarılır. Gerçek VoiceOver sırası bazı özel düzenlerde bundan farklı olabilir. Gerçek VoiceOver hareketiyle tarama, telefonlarda test edildikten sonra eklenecek ([PLANLAMA.md](PLANLAMA.md) Faz 0). Odak sırası hatalarında en kesin kanıt şimdilik video modu.
- **Ajan modunda ses yok.** Appium'un ekran kaydı ses almaz. Bu yüzden ajan modunda "duyulan" metin ağaçtan çıkarılır. Sesli analiz için video modunu kullan.
- **Konuşma tanıma Türkçe fonetiği karıştırabilir.** Türkçe ses İngilizce etiketleri Türkçe fonetikle okuduğu için tanıma bunları bozuk yazabilir (ör. "Back arrow" → "bekeroğu"). Yeni örnek gördükçe checks.yaml'daki `fonetik_kaliplar` listesine ekleyin.
- **Android ekran kaydı süresi:** Appium ile en fazla 30 dakika.
