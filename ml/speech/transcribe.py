"""Speech-to-text for the RWC Rohingya–English app.

One public entry point:

    from ml.speech import transcribe
    result = transcribe("clip.m4a", language="bn")
    result.text, result.confidence, result.status
    result.confidence_level, result.action, result.reason

Contract
--------
* Input: a file path, raw bytes, or a binary file-like object (e.g. FastAPI's
  ``UploadFile.file``). Any format ffmpeg can decode: m4a/AAC (what Expo records),
  wav, mp3, ogg/opus, webm, flac.
* Output: a ``TranscriptionResult`` with ``text``, ``confidence`` (0..1), a
  ``confidence_level`` (high/medium/low) and an ``action`` saying what the caller
  should do next: use the text, confirm it, ask the user to repeat, or stop asking.
* Never raises on bad audio. Empty, corrupt, silent, too-short and too-long audio,
  and model failures, all come back as a result with a non-``ok`` ``status`` and a
  short ``error`` message. Only programmer errors (an unsupported language code,
  a wrong argument type, an attempt below 1) raise.

Rohingya is not one of Whisper's languages, so ``language`` is a proxy setting
(``"bn"``, ``"ur"``, ``"en"`` or ``None`` for auto-detect). Which one works best on
Rohingya is what Hari's evaluation decides; it's a parameter so nobody has to edit
this file when that answer changes.
"""

from __future__ import annotations

import math
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Optional, Protocol, Union

import numpy as np

# --------------------------------------------------------------------------- config

SAMPLE_RATE = 16_000
MIN_DURATION_S = 0.3  # shorter than this can't hold a word
MAX_DURATION_S = 60.0  # app clips are a word or a sentence; keeps request time bounded
MAX_BYTES = 25 * 1024 * 1024  # reject before decoding anything this big

# A clip counts as silent when even its loudest 30 ms frame is below this RMS
# (about -50 dBFS). Frame-based so one quiet word in a long pause still counts.
SILENCE_RMS = 0.003
FRAME_S = 0.03

# Confidence bands for the model in DEFAULT_MODEL. At or above HIGH_CONFIDENCE the text
# is used as is; below LOW_CONFIDENCE it isn't trusted and the user is asked to repeat;
# in between the user confirms it. Re-derive with calibrate.py (see the README).
HIGH_CONFIDENCE = 0.7
LOW_CONFIDENCE = 0.5

# How many times a user is asked to record in total before the app stops asking.
MAX_ATTEMPTS = 3

# Whisper flags repetitive (likely hallucinated) output with a high compression ratio.
HALLUCINATION_COMPRESSION_RATIO = 2.4

DEFAULT_MODEL = os.getenv("RWC_WHISPER_MODEL", "small")
DEFAULT_DEVICE = os.getenv("RWC_WHISPER_DEVICE", "auto")  # "cpu", "cuda" or "auto"
DEFAULT_COMPUTE_TYPE = os.getenv("RWC_WHISPER_COMPUTE", "int8")

AudioInput = Union[str, os.PathLike, bytes, bytearray, BinaryIO]


class Status(str, Enum):
    OK = "ok"
    EMPTY_AUDIO = "empty_audio"  # zero bytes / zero samples
    INVALID_AUDIO = "invalid_audio"  # missing file, not audio, can't decode
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    NO_SPEECH = "no_speech"  # silent, or the model heard nothing
    MODEL_ERROR = "model_error"  # model failed to load or run


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Action(str, Enum):
    """What the caller should do with a result."""

    ACCEPT = "accept"  # high confidence: use the text
    CONFIRM = "confirm"  # medium confidence: show the text, ask "did you say this?"
    ASK_REPEAT = "ask_repeat"  # low confidence or unusable audio: ask the user to say it again
    FALLBACK = "fallback"  # still unusable on the last attempt: stop asking, offer another way
    RETRY_LATER = "retry_later"  # server failure: the user did nothing wrong, repeating won't help


@dataclass
class Segment:
    start: float
    end: float
    text: str
    confidence: float


@dataclass
class TranscriptionResult:
    status: Status
    text: str = ""
    confidence: float = 0.0
    language: Optional[str] = None  # language Whisper used (the proxy, not "Rohingya")
    language_probability: Optional[float] = None
    duration_s: Optional[float] = None
    processing_s: Optional[float] = None
    segments: list[Segment] = field(default_factory=list)
    error: Optional[str] = None
    attempt: int = 1  # which try this was for the same phrase, starting at 1

    @property
    def ok(self) -> bool:
        return self.status == Status.OK

    @property
    def is_confident(self) -> bool:
        return self.ok and self.confidence >= LOW_CONFIDENCE

    @property
    def confidence_level(self) -> Optional[ConfidenceLevel]:
        """High, medium or low; None when there is no transcription to rate."""
        if not self.ok:
            return None
        weakest = min((s.confidence for s in self.segments), default=None)
        return classify_confidence(self.confidence, weakest)

    @property
    def reason(self) -> Optional[str]:
        """Why the user needs to record again, so the app can say what to do differently.

        "low_confidence" or a failure status such as "no_speech" or "too_short". None
        when the text is usable, or on a server failure (not something to fix by repeating).
        """
        if self.status == Status.MODEL_ERROR:
            return None
        if not self.ok:
            return self.status.value
        return "low_confidence" if self.confidence_level == ConfidenceLevel.LOW else None

    @property
    def action(self) -> Action:
        if self.status == Status.MODEL_ERROR:
            return Action.RETRY_LATER
        level = self.confidence_level
        if level == ConfidenceLevel.HIGH:
            return Action.ACCEPT
        if level == ConfidenceLevel.MEDIUM:
            return Action.CONFIRM
        return Action.ASK_REPEAT if self.attempt < MAX_ATTEMPTS else Action.FALLBACK

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict for API responses."""
        d = asdict(self)
        d["status"] = self.status.value
        d["is_confident"] = self.is_confident
        level = self.confidence_level
        d["confidence_level"] = level.value if level else None
        d["action"] = self.action.value
        d["reason"] = self.reason
        return d


# --------------------------------------------------------------------------- model


class _Model(Protocol):
    def transcribe(self, audio: np.ndarray, **kwargs: Any) -> tuple[Any, Any]: ...


_models: dict[tuple[str, str, str], Any] = {}
_models_lock = threading.Lock()


def get_model(
    model_size: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
) -> Any:
    """Load a faster-whisper model once per process and reuse it."""
    key = (model_size, device, compute_type)
    with _models_lock:
        if key not in _models:
            from faster_whisper import WhisperModel

            _models[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
        return _models[key]


def warmup(model_size: str = DEFAULT_MODEL) -> None:
    """Load the model ahead of the first request (call from FastAPI startup)."""
    get_model(model_size)


def supported_languages() -> list[str]:
    from faster_whisper.tokenizer import _LANGUAGE_CODES

    return sorted(_LANGUAGE_CODES)


# --------------------------------------------------------------------------- audio


class _AudioError(Exception):
    def __init__(self, status: Status, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _read_bytes(audio: AudioInput) -> tuple[Optional[str], Optional[bytes]]:
    """Return (path, None) for paths or (None, data) for bytes / file objects."""
    if isinstance(audio, (str, os.PathLike)):
        path = Path(audio)
        if not path.is_file():
            raise _AudioError(Status.INVALID_AUDIO, f"file not found: {path}")
        size = path.stat().st_size
        if size == 0:
            raise _AudioError(Status.EMPTY_AUDIO, "audio file is empty")
        if size > MAX_BYTES:
            raise _AudioError(Status.TOO_LONG, f"audio file is too large ({size} bytes)")
        return str(path), None

    if isinstance(audio, (bytes, bytearray)):
        data = bytes(audio)
    elif hasattr(audio, "read"):
        data = audio.read(MAX_BYTES + 1)
        if isinstance(data, str):
            raise TypeError("file object must be opened in binary mode")
    else:
        raise TypeError(f"unsupported audio input type: {type(audio).__name__}")

    if not data:
        raise _AudioError(Status.EMPTY_AUDIO, "audio is empty")
    if len(data) > MAX_BYTES:
        raise _AudioError(Status.TOO_LONG, "audio is too large")
    return None, data


def _decode(path: str) -> np.ndarray:
    """Decode with PyAV straight to 16 kHz mono.

    Done here rather than with faster_whisper.audio.decode_audio, which breaks on
    PyAV >= 15 (it passes an ``open()`` argument PyAV removed).
    """
    import av

    chunks = []
    with av.open(path) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("no audio stream found")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):  # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def load_audio(audio: AudioInput) -> np.ndarray:
    """Decode any supported input to 16 kHz mono float32. Raises _AudioError."""
    path, data = _read_bytes(audio)
    tmp = None
    try:
        if data is not None:
            # m4a from phones often has its index at the end of the file, so it
            # can't be decoded from a stream. A temp file is the reliable route.
            tmp = tempfile.NamedTemporaryFile(suffix=".audio", delete=False)
            tmp.write(data)
            tmp.close()
            path = tmp.name
        try:
            samples = _decode(path)
        except Exception as e:  # PyAV raises several error types for bad input
            # PyAV's message ends with the file name, which for bytes input is a
            # server temp path; keep just the reason.
            reason = getattr(e, "strerror", None) or str(e)
            raise _AudioError(Status.INVALID_AUDIO, f"could not decode audio: {reason}") from e
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        raise _AudioError(Status.EMPTY_AUDIO, "audio has no samples")
    if not np.all(np.isfinite(samples)):
        raise _AudioError(Status.INVALID_AUDIO, "audio contains invalid samples")
    return samples


def _is_silent(samples: np.ndarray) -> bool:
    frame = max(1, int(FRAME_S * SAMPLE_RATE))
    n = samples.size // frame
    if n == 0:
        return float(np.sqrt(np.mean(samples**2))) < SILENCE_RMS
    frames = samples[: n * frame].reshape(n, frame)
    loudest = float(np.sqrt(np.mean(frames**2, axis=1)).max())
    return loudest < SILENCE_RMS


# --------------------------------------------------------------------------- confidence


def segment_confidence(avg_logprob: float, no_speech_prob: float, compression_ratio: float) -> float:
    """Turn Whisper's per-segment scores into a 0..1 confidence.

    exp(avg_logprob) is the geometric-mean token probability; it's scaled down by
    the chance the segment isn't speech at all, and halved when the text looks like
    a repetition loop (a common Whisper hallucination on noisy or unfamiliar audio).
    """
    p = math.exp(min(0.0, avg_logprob)) if math.isfinite(avg_logprob) else 0.0
    p *= 1.0 - min(max(no_speech_prob, 0.0), 1.0)
    if compression_ratio > HALLUCINATION_COMPRESSION_RATIO:
        p *= 0.5
    return min(max(p, 0.0), 1.0)


def _overall_confidence(segments: list[Segment]) -> float:
    """Duration-weighted mean, so a long clear segment outweighs a short noisy one."""
    if not segments:
        return 0.0
    weights = [max(s.end - s.start, 0.01) for s in segments]
    return sum(w * s.confidence for w, s in zip(weights, segments)) / sum(weights)


def classify_confidence(confidence: float, weakest_segment: Optional[float] = None) -> ConfidenceLevel:
    """Sort a clip score into a band.

    The clip score is a mean, so a clear sentence can hide a garbled phrase. One
    segment below LOW_CONFIDENCE therefore rules out HIGH, and the user gets to check.
    """
    if confidence < LOW_CONFIDENCE:
        return ConfidenceLevel.LOW
    if confidence < HIGH_CONFIDENCE:
        return ConfidenceLevel.MEDIUM
    if weakest_segment is not None and weakest_segment < LOW_CONFIDENCE:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


# --------------------------------------------------------------------------- main


def transcribe(
    audio: AudioInput,
    language: Optional[str] = None,
    *,
    model_size: str = DEFAULT_MODEL,
    model: Optional[_Model] = None,
    vad_filter: bool = True,
    beam_size: int = 5,
    attempt: int = 1,
) -> TranscriptionResult:
    """Transcribe one clip. Returns a result instead of raising on bad audio.

    Args:
        audio: path, bytes or binary file object.
        language: Whisper language code used as a proxy for Rohingya ("bn", "ur",
            "en", ...), or None to let Whisper detect it.
        model_size: faster-whisper model name ("tiny", "base", "small", "medium",
            "large-v3", ...). Ignored when ``model`` is given.
        model: an already-loaded model (mainly for tests).
        vad_filter: drop non-speech stretches before decoding; cuts hallucinated
            text on pauses and background noise.
        beam_size: Whisper beam size; 1 is faster, 5 is more accurate.
        attempt: which try this is for the same phrase, starting at 1. The caller
            counts (this function keeps no state between clips). On attempt
            MAX_ATTEMPTS, an unusable result returns FALLBACK instead of ASK_REPEAT.
    """
    if attempt < 1:
        raise ValueError(f"attempt starts at 1, got {attempt}")
    if language is not None:
        language = language.lower()
        if language not in supported_languages():
            raise ValueError(
                f"Whisper has no language code {language!r}. Rohingya isn't supported "
                "directly; use a proxy such as 'bn', 'ur' or 'en', or None to auto-detect."
            )

    started = time.perf_counter()

    def done(result: TranscriptionResult) -> TranscriptionResult:
        result.processing_s = round(time.perf_counter() - started, 3)
        result.attempt = attempt
        return result

    # 1. Decode and validate the audio before touching the model.
    try:
        samples = load_audio(audio)
    except _AudioError as e:
        return done(TranscriptionResult(status=e.status, error=e.message))

    duration = round(samples.size / SAMPLE_RATE, 3)
    if duration < MIN_DURATION_S:
        return done(TranscriptionResult(
            status=Status.TOO_SHORT, duration_s=duration,
            error=f"audio is {duration:.2f}s; need at least {MIN_DURATION_S}s",
        ))
    if duration > MAX_DURATION_S:
        return done(TranscriptionResult(
            status=Status.TOO_LONG, duration_s=duration,
            error=f"audio is {duration:.1f}s; limit is {MAX_DURATION_S:.0f}s",
        ))
    if _is_silent(samples):
        return done(TranscriptionResult(
            status=Status.NO_SPEECH, duration_s=duration, error="audio is silent",
        ))

    # 2. Run the model.
    try:
        m = model if model is not None else get_model(model_size)
        raw_segments, info = m.transcribe(
            samples,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            # Clips are short and independent; carrying text forward only feeds loops.
            condition_on_previous_text=False,
        )
        segments = [
            Segment(
                start=round(float(s.start), 3),
                end=round(float(s.end), 3),
                text=s.text.strip(),
                confidence=round(segment_confidence(
                    float(s.avg_logprob), float(s.no_speech_prob), float(s.compression_ratio),
                ), 4),
            )
            for s in raw_segments  # a generator: decoding actually happens here
        ]
    except Exception as e:
        return done(TranscriptionResult(
            status=Status.MODEL_ERROR, duration_s=duration,
            error=f"transcription failed: {type(e).__name__}: {e}",
        ))

    segments = [s for s in segments if s.text]
    lang = getattr(info, "language", language)
    lang_p = getattr(info, "language_probability", None)
    if not segments:
        return done(TranscriptionResult(
            status=Status.NO_SPEECH, duration_s=duration, language=lang,
            language_probability=lang_p, error="no speech recognised",
        ))

    return done(TranscriptionResult(
        status=Status.OK,
        text=" ".join(s.text for s in segments),
        confidence=round(_overall_confidence(segments), 4),
        language=lang,
        language_probability=round(lang_p, 4) if lang_p is not None else None,
        duration_s=duration,
        segments=segments,
    ))
