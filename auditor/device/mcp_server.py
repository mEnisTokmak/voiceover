"""Telefon araçlarını MCP (stdio) üzerinden Claude Code CLI'ye açar.

    python -m auditor.device.mcp_server --aid <denetim> --platform ios|android --app pegasus
"""
from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP, Image

from .session import DeviceSession


def build(dev: DeviceSession) -> FastMCP:
    mcp = FastMCP("cihaz")

    def out(r):
        return Image(path=r["image"]) if isinstance(r, dict) and "image" in r else r

    @mcp.tool(description="Telefonun güncel ekran görüntüsünü al.")
    def ekran_goruntusu():
        return out(dev.call("ekran_goruntusu", {}))

    @mcp.tool(description="Ekrandaki öğeleri listele (indeks, etiket, rol, konum). Dokunmak için indeks kullan.")
    def ogeler() -> str:
        return dev.call("ogeler", {})

    @mcp.tool(description="ogeler listesindeki indeksi verilen öğeye dokun.")
    def dokun(indeks: int) -> str:
        return dev.call("dokun", {"indeks": indeks})

    @mcp.tool(description="Cihaz koordinatına dokun (ogeler'deki konum birimiyle).")
    def dokun_koordinat(x: int, y: int) -> str:
        return dev.call("dokun_koordinat", {"x": x, "y": y})

    @mcp.tool(description="Bir metin alanına yaz. indeks verilirse önce o alana dokunur.")
    def yaz(metin: str, indeks: int | None = None) -> str:
        return dev.call("yaz", {"metin": metin, "indeks": indeks})

    @mcp.tool(description="Ekranı kaydır. yon: asagi | yukari | sola | saga.")
    def kaydir(yon: str) -> str:
        return dev.call("kaydir", {"yon": yon})

    @mcp.tool(description="Bir önceki ekrana dön.")
    def geri() -> str:
        return dev.call("geri", {})

    @mcp.tool(description="Bu ekranı ekran okuyucu gözüyle tara ve analiz için kaydet. Her yeni ekranda bir kez çağır.")
    def ekran_okuyucu_taramasi(ekran_adi: str) -> str:
        return dev.call("ekran_okuyucu_taramasi", {"ekran_adi": ekran_adi})

    @mcp.tool(description="Senaryo bitti; kısa özetle oturumu kapat.")
    def bitir(ozet: str) -> str:
        return dev.call("bitir", {"ozet": ozet})

    return mcp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aid", required=True)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--app", required=True)
    a = ap.parse_args()
    dev = DeviceSession(a.aid, a.platform, a.app)
    try:
        build(dev).run()
    finally:
        dev.close()


if __name__ == "__main__":
    main()
