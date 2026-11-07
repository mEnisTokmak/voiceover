"""ffmpeg yardımcıları: ses ayırma, kare çıkarma, klip kesme."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} hatası: {p.stderr[-800:]}")
    return p.stdout


def duration(video: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)])
    return float(json.loads(out)["format"]["duration"])


def has_audio(video: Path) -> bool:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(video)])
    return bool(json.loads(out).get("streams"))


def extract_audio(video: Path, out: Path) -> Path:
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-ac", "1", "-ar", "16000", str(out)])
    return out


def frame_at(video: Path, t: float, out: Path, width: int = 540) -> Path:
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(t, 0):.2f}", "-i", str(video),
          "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)])
    return out


def keyframes(video: Path, segments: list[dict], outdir: Path, max_frames: int = 24) -> list[dict]:
    """Ekran okuyucunun her konuşmasının başındaki kare (odak çerçevesi o anda yeni öğededir).
    Konuşma yoksa her 2 sn'de bir kare."""
    outdir.mkdir(parents=True, exist_ok=True)
    dur = duration(video)
    times = [min(s["start"] + 0.35, dur - 0.05) for s in segments] or [t * 2.0 for t in range(int(dur // 2) + 1)]
    times = [0.2] + times
    uniq: list[float] = []
    for t in sorted(times):
        if not uniq or t - uniq[-1] >= 0.5:
            uniq.append(t)
    if len(uniq) > max_frames:
        step = len(uniq) / max_frames
        uniq = [uniq[int(i * step)] for i in range(max_frames)]
    frames = []
    for i, t in enumerate(uniq):
        p = frame_at(video, t, outdir / f"kare_{i:03d}_{t:06.2f}s.jpg")
        frames.append({"t": round(t, 2), "yol": str(p)})
    return frames


def clip(video: Path, start: float, end: float, out: Path, pad: float = 3.0) -> Path:
    dur = duration(video)
    s = max(0.0, start - pad)
    e = min(dur, max(end, start) + pad)
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.2f}", "-to", f"{e:.2f}", "-i", str(video),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-movflags", "+faststart", str(out)])
    return out
