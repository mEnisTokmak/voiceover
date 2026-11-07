"""Ajan: senaryoyu telefonda uygular, her ekranı ekran okuyucu gözüyle tarar, sonra analizi başlatır."""
from __future__ import annotations

import json
import os
import sys

from . import llm, store
from .analysis import pipeline
from .config import CONFIG_DIR, DATA_DIR, ROOT, app_profile, read_text, settings
from .device.session import TOOL_SPECS, DeviceSession


def build_prompt(audit: dict, senaryo: str) -> str:
    prof = app_profile(audit["uygulama"])
    tpl = read_text("prompts/ajan.md")
    for k, v in {"{platform}": audit["platform"], "{uygulama}": prof.get("ad", audit["uygulama"]),
                 "{senaryo}": senaryo}.items():
        tpl = tpl.replace(k, v)
    return tpl


def run(aid: str) -> None:
    audit = store.get_audit(aid)
    senaryo = audit["senaryo"] or ""
    ad = senaryo.strip().removesuffix(".md")
    if "\n" not in ad and (CONFIG_DIR / "scenarios" / f"{ad}.md").exists():
        senaryo = read_text(f"scenarios/{ad}.md")
    prompt = build_prompt(audit, senaryo)
    store.set_audit(aid, durum="ajan çalışıyor")
    b = llm.backend_name()
    store.log(aid, f"Ajan başlıyor (arka uç: {b}).")
    try:
        if b == "cli":
            _run_cli(aid, audit, prompt)
        elif b == "api":
            _run_api(aid, audit, prompt)
        else:
            raise llm.LLMError("Ajan için LLM_BACKEND=cli veya api olmalı.")
    except Exception as e:
        store.log(aid, f"Ajan hatası: {e}")
    pipeline.analyze_agent_session(aid)


def _run_cli(aid: str, audit: dict, prompt: str) -> None:
    sdir = store.session_path(aid)
    cfg = {"mcpServers": {"cihaz": {
        "command": sys.executable,
        "args": ["-m", "auditor.device.mcp_server", "--aid", aid, "--platform", audit["platform"], "--app", audit["uygulama"]],
        "env": {"PYTHONPATH": str(ROOT), "DATA_DIR": str(DATA_DIR), "CONFIG_DIR": str(CONFIG_DIR),
                "APPIUM_URL": settings()["appium"]["url"], "PATH": os.environ.get("PATH", "")},
    }}}
    mcp_json = sdir / "mcp.json"
    mcp_json.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    data = llm.run_cli_agent(prompt, mcp_json, sdir, "mcp__cihaz")
    store.log(aid, f"Ajan özeti: {str(data.get('result', ''))[:600]}")


def _run_api(aid: str, audit: dict, prompt: str) -> None:
    import anthropic
    client = anthropic.Anthropic()
    s = settings()
    dev = DeviceSession(aid, audit["platform"], audit["uygulama"])
    messages: list[dict] = [{"role": "user", "content": prompt}]
    try:
        for _ in range(s.get("ajan", {}).get("en_fazla_adim", 150)):
            resp = client.messages.create(model=s["llm"].get("api_agent_model", "claude-opus-5-5"), max_tokens=4096,
                                          tools=TOOL_SPECS, messages=messages)
            messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
            if resp.stop_reason != "tool_use":
                break
            results = []
            for b in resp.content:
                if b.type != "tool_use":
                    continue
                r = dev.call(b.name, b.input)
                if isinstance(r, dict) and "image" in r:
                    from pathlib import Path
                    content = [llm.image_block(Path(r["image"]))]
                else:
                    content = [{"type": "text", "text": str(r)}]
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
            messages.append({"role": "user", "content": results})
            _prune_images(messages, keep=2)
            if dev.done:
                break
    finally:
        dev.close()


def _prune_images(messages: list[dict], keep: int) -> None:
    """Bağlamı küçük tutmak için yalnız son `keep` ekran görüntüsünü bırak."""
    seen = 0
    for m in reversed(messages):
        if m["role"] != "user" or not isinstance(m["content"], list):
            continue
        for tr in m["content"]:
            if tr.get("type") != "tool_result":
                continue
            for i, c in enumerate(tr["content"]):
                if c.get("type") == "image":
                    seen += 1
                    if seen > keep:
                        tr["content"][i] = {"type": "text", "text": "[eski ekran görüntüsü kaldırıldı]"}
