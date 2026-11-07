"""Yapılandırma okuma. Dosyalar her çağrıda diskten okunur; panelden yapılan değişiklik anında geçerlidir."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))

# Panelden düzenlenebilen dosyalar (CONFIG_DIR'e göre)
EDITABLE_GLOBS = ["settings.yaml", "wcag_katalog.yaml", "checks.yaml", "prompts/*.md", "apps/*.yaml", "scenarios/*.md"]


def load_yaml(rel: str) -> dict:
    with open(CONFIG_DIR / rel, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_text(rel: str) -> str:
    return (CONFIG_DIR / rel).read_text(encoding="utf-8")


def settings() -> dict:
    s = load_yaml("settings.yaml")
    if os.environ.get("LLM_BACKEND"):
        s.setdefault("llm", {})["backend"] = os.environ["LLM_BACKEND"]
    if os.environ.get("APPIUM_URL"):
        s.setdefault("appium", {})["url"] = os.environ["APPIUM_URL"]
    return s


def catalog() -> list[dict]:
    return load_yaml("wcag_katalog.yaml").get("hata_turleri", [])


def catalog_by_name() -> dict[str, dict]:
    return {h["ad"]: h for h in catalog()}


def checks(enabled_only: bool = True) -> list[dict]:
    items = load_yaml("checks.yaml").get("kontroller", [])
    return [c for c in items if c.get("etkin", True)] if enabled_only else items


def app_profile(name: str) -> dict:
    return load_yaml(f"apps/{name}.yaml")


def list_apps() -> list[str]:
    return sorted(p.stem for p in (CONFIG_DIR / "apps").glob("*.yaml"))


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in (CONFIG_DIR / "scenarios").glob("*.md"))


def editable_files() -> list[str]:
    out: list[str] = []
    for g in EDITABLE_GLOBS:
        out += sorted(str(p.relative_to(CONFIG_DIR)) for p in CONFIG_DIR.glob(g))
    return out


def sessions_dir() -> Path:
    d = DATA_DIR / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d
