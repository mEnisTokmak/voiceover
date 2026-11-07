"""Yapay zekâ arka ucu: aynı arayüz, iki uygulama.

  backend=cli  -> `claude -p` (Claude aboneliği, CLAUDE_CODE_OAUTH_TOKEN veya yerel oturum)
  backend=api  -> Anthropic Messages API (ANTHROPIC_API_KEY)
  backend=none -> yapay zekâ yok (yalnız kural motoru)
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

from .config import settings


class LLMError(RuntimeError):
    pass


def backend_name() -> str:
    return settings().get("llm", {}).get("backend", "cli")


def structured(prompt: str, schema: dict, images: list[Path] | None = None, workdir: Path | None = None,
               agent: bool = False) -> dict:
    """Talimat + görseller -> şemaya uyan JSON (dict)."""
    b = backend_name()
    if b == "cli":
        return _cli(prompt, schema, images or [], workdir, agent)
    if b == "api":
        return _api(prompt, schema, images or [], agent)
    raise LLMError("LLM_BACKEND=none: yapay zekâ kapalı")


# ---------------------------------------------------------------- CLI
def _cli(prompt: str, schema: dict, images: list[Path], workdir: Path | None, agent: bool) -> dict:
    s = settings()["llm"]
    model = s.get("cli_agent_model" if agent else "cli_model", "sonnet")
    if images:
        listing = "\n".join(f"- {p}" for p in images)
        prompt = (f"Önce şu ekran görüntülerinin HEPSİNİ Read aracıyla aç ve incele:\n{listing}\n\n" + prompt)
    cmd = ["claude", "-p", "--output-format", "json", "--model", model,
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--allowedTools", "Read"]
    dirs = {str(p.parent) for p in images}
    if workdir:
        dirs.add(str(workdir))
    for d in sorted(dirs):
        cmd += ["--add-dir", d]
    return _run_cli(cmd, prompt, workdir, s.get("zaman_asimi_sn", 900))["structured_output"]


def run_cli_agent(prompt: str, mcp_config: Path, workdir: Path, allowed: str) -> dict:
    s = settings()["llm"]
    cmd = ["claude", "-p", "--output-format", "json", "--model", s.get("cli_agent_model", "opus"),
           "--mcp-config", str(mcp_config), "--strict-mcp-config", "--allowedTools", allowed]
    return _run_cli(cmd, prompt, workdir, max(3600, s.get("zaman_asimi_sn", 900)))


def _run_cli(cmd: list[str], prompt: str, workdir: Path | None, timeout: int) -> dict:
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                           cwd=str(workdir) if workdir else None, env=os.environ.copy())
    except FileNotFoundError as e:
        raise LLMError("claude CLI bulunamadı (npm i -g @anthropic-ai/claude-code)") from e
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"claude CLI çıktısı okunamadı: {p.stdout[:500]} {p.stderr[:500]}") from e
    if data.get("is_error"):
        raise LLMError(f"claude CLI hatası: {data.get('result') or data.get('subtype')}")
    return data


# ---------------------------------------------------------------- API
def _client():
    import anthropic
    return anthropic.Anthropic()


def image_block(p: Path) -> dict:
    mt = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": mt,
                                         "data": base64.b64encode(p.read_bytes()).decode()}}


def _api(prompt: str, schema: dict, images: list[Path], agent: bool) -> dict:
    s = settings()["llm"]
    content: list[dict] = []
    for p in images:
        content += [{"type": "text", "text": f"Görsel: {p.name}"}, image_block(p)]
    content.append({"type": "text", "text": prompt})
    resp = _client().messages.create(
        model=s.get("api_agent_model" if agent else "api_model", "claude-sonnet-5-5"),
        max_tokens=16000,
        tools=[{"name": "sonucu_kaydet", "description": "Sonucu yapılandırılmış olarak kaydet.",
                "input_schema": schema}],
        tool_choice={"type": "tool", "name": "sonucu_kaydet"},
        messages=[{"role": "user", "content": content}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise LLMError("API yanıtında yapılandırılmış sonuç yok")
