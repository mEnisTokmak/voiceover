"""Ekran okuyucu sesi -> zaman damgalı metin + her konuşma parçası için dil tespiti (faster-whisper)."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import DATA_DIR, settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        w = settings().get("whisper", {})
        _model = WhisperModel(w.get("model", "small"), device=w.get("device", "cpu"),
                              compute_type=w.get("compute_type", "int8"),
                              download_root=str(DATA_DIR / "models" / "whisper"))
    return _model


def _load_audio(path: Path):
    """ffmpeg ile 16 kHz mono float32 (PyAV sürüm uyumsuzluklarından bağımsız)."""
    import subprocess

    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def transcribe(audio: Path, cache: Path | None = None) -> list[dict]:
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    model = _get_model()
    wav = _load_audio(audio)
    segments, info = model.transcribe(wav, language=None, word_timestamps=True, beam_size=5,
                                      condition_on_previous_text=False, vad_filter=False)
    out = []
    for s in segments:
        text = s.text.strip()
        if not text:
            continue
        lang, prob = info.language, info.language_probability
        chunk = wav[int(s.start * 16000): int(s.end * 16000)]
        if len(chunk) > 16000 * 0.3:
            try:
                lang, prob, _ = model.detect_language(chunk)
            except Exception:  # eski sürümlerde yok -> genel dil
                pass
        out.append({
            "start": round(s.start, 2), "end": round(s.end, 2), "text": text,
            "dil": lang, "dil_olasilik": round(float(prob), 2),
            "kelimeler": [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
                          for w in (s.words or [])],
        })
    if cache:
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
