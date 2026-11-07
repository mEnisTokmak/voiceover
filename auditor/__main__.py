"""Komut satırı.

  python -m auditor analiz <video.mp4> --app pegasus --platform ios
  python -m auditor yeniden <denetim_id>          # aynı oturumu güncel kontrol/derslerle yeniden analiz et
  python -m auditor ajan --app pegasus --platform android --senaryo pegasus_ucus_arama
  python -m auditor drive-yetki
  python -m auditor drive <denetim_id> [--hepsini-onayla]
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import agent, store
from .analysis import pipeline
from .report import drive


def main() -> None:
    ap = argparse.ArgumentParser(prog="auditor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analiz")
    a.add_argument("video")
    a.add_argument("--app", default="pegasus")
    a.add_argument("--platform", default="ios")
    r = sub.add_parser("yeniden")
    r.add_argument("aid")
    g = sub.add_parser("ajan")
    g.add_argument("--app", default="pegasus")
    g.add_argument("--platform", default="android")
    g.add_argument("--senaryo", default="pegasus_ucus_arama")
    sub.add_parser("drive-yetki")
    d = sub.add_parser("drive")
    d.add_argument("aid")
    d.add_argument("--hepsini-onayla", action="store_true")
    args = ap.parse_args()

    if args.cmd == "analiz":
        aid = store.create_audit(args.app, args.platform, "video")
        src = Path(args.video)
        dst = store.session_path(aid) / ("video" + src.suffix)
        shutil.copy(src, dst)
        store.set_audit(aid, video_yolu=str(dst))
        pipeline.analyze_video(aid)
        _print(aid)
    elif args.cmd == "yeniden":
        au = store.get_audit(args.aid)
        (pipeline.analyze_video if au["tur"] == "video" else pipeline.analyze_agent_session)(args.aid)
        _print(args.aid)
    elif args.cmd == "ajan":
        aid = store.create_audit(args.app, args.platform, "ajan", senaryo=args.senaryo)
        agent.run(aid)
        _print(aid)
    elif args.cmd == "drive-yetki":
        drive.authorize()
    elif args.cmd == "drive":
        if args.hepsini_onayla:
            for f in store.findings(args.aid):
                if f["durum"] == "beklemede":
                    store.update_finding(f["id"], durum="onaylandi")
        print(drive.upload_audit(args.aid))


def _print(aid: str) -> None:
    print(f"\nDenetim: {aid}")
    for f in store.findings(aid):
        v = f["veri"]
        print(f["durum"].upper(), json.dumps({k: v.get(k) for k in ("baslik", "hata_turu", "wcag", "not", "guven", "baslangic_sn", "kontrol_id")},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
