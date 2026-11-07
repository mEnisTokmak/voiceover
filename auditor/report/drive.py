"""Google Drive + Sheets: onaylanan bulguları denetçinin formatında yükler.

İlk kurulum (bir kez):
  1. Google Cloud Console'da OAuth istemcisi (Masaüstü uygulaması) oluşturun, JSON'u
     data/secrets/client_secret.json olarak kaydedin.
  2. docker compose run --rm -p 8765:8765 auditor python -m auditor drive-yetki
     Çıkan bağlantıyı tarayıcıda açın, izin verin. Token data/secrets/token.json'a yazılır.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import store
from ..config import DATA_DIR, settings

SCOPES = ["https://www.googleapis.com/auth/drive"]
SECRETS = DATA_DIR / "secrets"
FOLDER = "application/vnd.google-apps.folder"
SHEET = "application/vnd.google-apps.spreadsheet"
BASLIKLAR = ["#", "Başlık", "Hata Türü", "WCAG Kriteri", "Seviye", "Not", "Çözüm Önerisi",
             "Platform", "Ekran", "Önem", "Video", "Kaynak"]


def authorize() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow
    SECRETS.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS / "client_secret.json"), SCOPES)
    creds = flow.run_local_server(host="localhost", bind_addr="0.0.0.0", port=8765, open_browser=False)
    (SECRETS / "token.json").write_text(creds.to_json(), encoding="utf-8")
    print("Drive yetkisi kaydedildi:", SECRETS / "token.json")


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    tok = SECRETS / "token.json"
    if not tok.exists():
        raise RuntimeError("Drive yetkisi yok. Önce: python -m auditor drive-yetki")
    creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        tok.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _services():
    from googleapiclient.discovery import build
    c = _creds()
    return build("drive", "v3", credentials=c, cache_discovery=False), build("sheets", "v4", credentials=c, cache_discovery=False)


def _folder(drive, name: str, parent: str | None) -> str:
    safe = name.replace("'", "\\'")
    qy = f"mimeType='{FOLDER}' and name='{safe}' and trashed=false" + (f" and '{parent}' in parents" if parent else " and 'root' in parents")
    found = drive.files().list(q=qy, fields="files(id)").execute().get("files", [])
    if found:
        return found[0]["id"]
    body = {"name": name, "mimeType": FOLDER, **({"parents": [parent]} if parent else {})}
    return drive.files().create(body=body, fields="id").execute()["id"]


def _upload(drive, path: Path, parent: str) -> str:
    from googleapiclient.http import MediaFileUpload
    mt = "video/mp4" if path.suffix == ".mp4" else "image/jpeg"
    f = drive.files().create(body={"name": path.name, "parents": [parent]},
                             media_body=MediaFileUpload(str(path), mimetype=mt, resumable=True),
                             fields="id,webViewLink").execute()
    return f["webViewLink"]


def _slug(s: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosuCGIOSU-")
    return "".join(ch for ch in s.translate(tr).lower() if ch.isalnum() or ch == "-")[:40]


def upload_audit(aid: str) -> str:
    audit = store.get_audit(aid)
    rows = [f for f in store.findings(aid) if f["durum"] == "onaylandi"]
    if not rows:
        raise RuntimeError("Onaylanmış bulgu yok.")
    drive, sheets = _services()
    d = settings().get("drive", {})
    root = d.get("kok_klasor_id") or _folder(drive, d.get("kok_klasor_adi", "Erişilebilirlik Denetimleri"), None)
    app_f = _folder(drive, audit["uygulama"].capitalize(), root)
    tarih = datetime.fromisoformat(audit["olusturma"]).strftime("%Y-%m-%d")
    run_f = _folder(drive, f"{tarih}_{audit['platform']}_{aid.split('_')[0]}", app_f)
    vid_f = _folder(drive, "Videolar", run_f)

    otomatik, ekstra = [], []
    for n, f in enumerate(rows, 1):
        v = f["veri"]
        link = ""
        media = f.get("klip_yolu") or f.get("gorsel_yolu")
        if media and Path(media).exists():
            p = Path(media)
            named = p.with_name(f"{n:03d}_{_slug(v.get('hata_turu', ''))}_{_slug(v.get('ekran', '') or v.get('baslik', ''))}{p.suffix}")
            if not named.exists():
                named.write_bytes(p.read_bytes())
            link = _upload(drive, named, vid_f)
        row = [n, v.get("baslik", ""), v.get("hata_turu", ""), ", ".join(v.get("wcag", [])), v.get("seviye", ""),
               v.get("not", ""), v.get("cozum_onerisi", ""), v.get("platform", audit["platform"]), v.get("ekran", ""),
               v.get("onem", ""), link, "Manuel (Ekstra)" if v.get("kaynak") == "manuel" else "Otomatik"]
        (ekstra if v.get("kaynak") == "manuel" else otomatik).append(row)

    sheet = drive.files().create(body={"name": "Bulgular", "mimeType": SHEET, "parents": [run_f]}, fields="id").execute()
    sid = sheets.spreadsheets().get(spreadsheetId=sheet["id"]).execute()
    first = sid["sheets"][0]["properties"]["sheetId"]
    sheets.spreadsheets().batchUpdate(spreadsheetId=sheet["id"], body={"requests": [
        {"updateSheetProperties": {"properties": {"sheetId": first, "title": "Bulgular"}, "fields": "title"}},
        {"addSheet": {"properties": {"title": "Ekstra"}}},
    ]}).execute()
    sheets.spreadsheets().values().update(spreadsheetId=sheet["id"], range="Bulgular!A1", valueInputOption="USER_ENTERED",
                                          body={"values": [BASLIKLAR] + otomatik}).execute()
    sheets.spreadsheets().values().update(spreadsheetId=sheet["id"], range="Ekstra!A1", valueInputOption="USER_ENTERED",
                                          body={"values": [BASLIKLAR] + ekstra}).execute()
    link = f"https://drive.google.com/drive/folders/{run_f}"
    store.set_audit(aid, drive_link=link, durum="yüklendi")
    store.log(aid, f"Drive'a yüklendi: {link}")
    return link
