"""TTS backends. A backend turns English text into audio samples.

Only free, key-less engines live here. To add another (for example a paid service the
team decides to adopt), write a class with the ``TTSBackend`` shape and register it:

    register_backend("my_engine", lambda **opts: MyEngine(**opts))

Keys for any such engine must come from environment variables, never from code or git.
Rohingya has no TTS: backends are only ever given English text.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

DEFAULT_BACKEND = os.getenv("RWC_TTS_BACKEND", "kokoro")
CACHE_DIR = Path(os.getenv("RWC_TTS_CACHE", Path.home() / ".cache" / "rwc-tts"))

KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# espeak-ng keeps its data path in a short fixed buffer and silently falls back to a
# build-machine path when the real one is too long (deep virtualenv or synced folders).
_ESPEAK_MAX_PATH = 120


class TTSBackend(Protocol):
    name: str
    voice: str
    license_note: str

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Return mono float32 samples in [-1, 1] and the sample rate."""
        ...


# --------------------------------------------------------------------------- kokoro


def kokoro_files() -> tuple[Path, Path]:
    return (
        Path(os.getenv("RWC_KOKORO_MODEL", CACHE_DIR / "kokoro-v1.0.int8.onnx")),
        Path(os.getenv("RWC_KOKORO_VOICES", CACHE_DIR / "voices-v1.0.bin")),
    )


def fetch_kokoro_files() -> list[Path]:
    """Download the Kokoro model files (about 120 MB, public, no key). Skips existing."""
    done = []
    for path, url in zip(kokoro_files(), (KOKORO_MODEL_URL, KOKORO_VOICES_URL)):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(path)
        done.append(path)
    return done


def _espeak_data_dir() -> str:
    import espeakng_loader

    data = Path(espeakng_loader.get_data_path())
    if len(str(data)) <= _ESPEAK_MAX_PATH:
        return str(data)
    short = Path(tempfile.gettempdir()) / "rwc-espeak" / "espeak-ng-data"
    if not short.exists():
        shutil.copytree(data, short)
    return str(short)


class KokoroBackend:
    """Kokoro-82M (int8 ONNX). Apache-2.0 weights, runs locally on CPU, no key."""

    name = "kokoro"
    license_note = (
        "Kokoro-82M weights Apache-2.0 (hexgrad/Kokoro-82M); kokoro-onnx MIT. "
        "Model card lists CC BY training data (Koniwa, SIWIS): credit in app credits."
    )

    def __init__(self, voice: str = "af_heart", speed: float = 0.9, lang: str = "en-us") -> None:
        self.voice, self.speed, self.lang = voice, speed, lang
        self._kokoro: Any = None

    def _load(self) -> Any:
        if self._kokoro is None:
            import espeakng_loader
            from kokoro_onnx import EspeakConfig, Kokoro

            model, voices = kokoro_files()
            if not (model.exists() and voices.exists()):
                raise FileNotFoundError(
                    f"Kokoro model files not found ({model}, {voices}). "
                    "Run: python -m ml.tts fetch-model"
                )
            cfg = EspeakConfig(lib_path=espeakng_loader.get_library_path(), data_path=_espeak_data_dir())
            self._kokoro = Kokoro(str(model), str(voices), espeak_config=cfg)
        return self._kokoro

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        samples, rate = self._load().create(text, voice=self.voice, speed=self.speed, lang=self.lang)
        return np.asarray(samples, dtype=np.float32), int(rate)


# --------------------------------------------------------------------------- registry

_BACKENDS: dict[str, Callable[..., TTSBackend]] = {"kokoro": KokoroBackend}


def register_backend(name: str, factory: Callable[..., TTSBackend]) -> None:
    _BACKENDS[name] = factory


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


def get_backend(name: str | None = None, **options: Any) -> TTSBackend:
    name = name or DEFAULT_BACKEND
    if name not in _BACKENDS:
        raise ValueError(f"unknown TTS backend {name!r}; available: {', '.join(available_backends())}")
    return _BACKENDS[name](**options)


# --------------------------------------------------------------------------- encoding


def to_mp3(samples: np.ndarray, rate: int) -> bytes:
    """Encode mono float samples as mp3 with PyAV (bundled ffmpeg, no system install)."""
    import av

    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp3") as out:
        stream = out.add_stream("mp3", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = rate
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()
