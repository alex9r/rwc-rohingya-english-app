"""Pronunciation scoring for the RWC Rohingya–English app.

One public entry point:

    from ml.pronunciation import score_pronunciation
    result = score_pronunciation("clip.m4a", "I need a doctor")
    result.score, result.feedback, result.needs_improvement

How it works
------------
1. ``ml.speech.transcribe`` turns the clip into English text (``language="en"``;
   learners practise spoken English, and Whisper has no Rohingya anyway).
2. Target and transcript are normalised (case, punctuation, contractions, digits).
3. The words are aligned (edit-distance alignment with fuzzy word matching).
4. The score is the share of target words that were heard, 0-100.

This is an ASR match: it measures whether Whisper understood the learner, i.e.
intelligibility. It does not look at phonemes, and Whisper tends to "autocorrect"
accented speech toward the expected words, so scores can be generous. Every result
is marked ``provisional`` until the thresholds are calibrated (Hari's evaluation).

Never raises. Bad audio, a missing target, low ASR confidence and model failures all
come back as a result with a non-``scored`` status and ``score=None``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ml.speech import LOW_CONFIDENCE
from ml.speech.transcribe import AudioInput, Status, TranscriptionResult
from ml.speech.transcribe import transcribe as _default_transcribe

try:
    from rapidfuzz.fuzz import ratio as _ratio

    def _similarity(a: str, b: str) -> float:
        return _ratio(a, b) / 100.0

except ImportError:  # difflib ships with Python; slightly different scores, same idea
    from difflib import SequenceMatcher

    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


# --------------------------------------------------------------------------- config

LANGUAGE = "en"
MAX_SCORE = 100
SCORE_BASIS = "asr_match"

# Below this ASR confidence the transcript is not trusted and no score is given.
# UNCALIBRATED: follows ml.speech.LOW_CONFIDENCE so the two stay in step when Hari
# calibrates; override per call with ``min_confidence``.
MIN_CONFIDENCE = LOW_CONFIDENCE

# Two words count as "the same word, said slightly differently" at or above this
# string similarity (0-1). UNCALIBRATED. "doctors"/"doctor" = 0.92, "ship"/"sheep" = 0.67.
DEFAULT_FUZZY_THRESHOLD = 0.8

# An inserted extra word costs half a missed word in the score.
EXTRA_WORD_WEIGHT = 0.5

# Score bands for the feedback message. UNCALIBRATED, chosen only to give encouraging,
# non-diagnostic wording.
GREAT_AT = 90
GOOD_AT = 70
KEEP_GOING_AT = 40

# Issue labels in needs_improvement.
ISSUE_MISSED = "missed"  # target word not heard
ISSUE_DIFFERENT = "different"  # a different word was heard instead
ISSUE_CLOSE = "close"  # heard something very similar (e.g. a different ending)
ISSUE_EXTRA = "extra"  # an extra word that is not in the target

STATUS_SCORED = "scored"
STATUS_UNAVAILABLE = "scoring_unavailable"

# --------------------------------------------------------------------------- normalisation

_IRREGULAR_CONTRACTIONS = {
    "can't": "can not", "cannot": "can not", "won't": "will not", "shan't": "shall not",
    "ain't": "is not", "let's": "let us", "y'all": "you all", "gonna": "going to",
    "wanna": "want to", "gotta": "got to",
}
_CONTRACTION_SUFFIXES = [
    ("n't", " not"), ("'re", " are"), ("'ve", " have"), ("'ll", " will"),
    ("'m", " am"), ("'d", " would"),
]
# "'s" is "is" after these, otherwise a possessive and dropped.
_S_IS = {"it", "that", "there", "here", "what", "who", "where", "how", "he", "she"}

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        rest = f" {_number_to_words(n % 100)}" if n % 100 else ""
        return f"{_ONES[n // 100]} hundred{rest}"
    if n < 1_000_000:
        rest = f" {_number_to_words(n % 1000)}" if n % 1000 else ""
        return f"{_number_to_words(n // 1000)} thousand{rest}"
    return str(n)


# Words an ASR cannot tell apart, so a learner must not be marked wrong for them.
# Deliberately small; extend when the evaluation shows real cases.
_HOMOPHONE_GROUPS = [
    {"to", "too", "two"}, {"there", "their", "theyre"}, {"your", "youre"},
    {"for", "four", "fore"}, {"no", "know"}, {"right", "write"}, {"here", "hear"},
    {"see", "sea"}, {"one", "won"}, {"by", "buy", "bye"}, {"our", "hour"},
    {"would", "wood"}, {"son", "sun"}, {"week", "weak"}, {"blue", "blew"},
    {"eight", "ate"}, {"meet", "meat"}, {"whole", "hole"}, {"be", "bee"},
    {"wait", "weight"}, {"sale", "sail"}, {"pair", "pear", "pare"},
    {"tire", "tyre"}, {"flour", "flower"}, {"mail", "male"}, {"plane", "plain"},
]
_HOMOPHONES = {w: i for i, g in enumerate(_HOMOPHONE_GROUPS) for w in g}


def _expand_contractions(token: str) -> str:
    if token in _IRREGULAR_CONTRACTIONS:
        return _IRREGULAR_CONTRACTIONS[token]
    for suffix, repl in _CONTRACTION_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            return token[: -len(suffix)] + repl
    if token.endswith("'s") and len(token) > 2:
        stem = token[:-2]
        return f"{stem} is" if stem in _S_IS else stem
    return token


def normalize(text: str) -> list[str]:
    """Lowercase, expand contractions, spell out digits, strip punctuation -> word list.

    >>> normalize("I'm 2 years old, Doctor!")
    ['i', 'am', 'two', 'years', 'old', 'doctor']
    """
    if not isinstance(text, str):
        return []
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,000 -> 1000
    text = re.sub(r"[-–—_/]", " ", text)  # twenty-one -> twenty one
    words: list[str] = []
    for token in text.split():
        token = re.sub(r"^[^\w']+|[^\w']+$", "", token)  # trim surrounding punctuation
        token = _expand_contractions(token)
        for part in token.split():
            part = re.sub(r"[^\w]", "", part)  # drop any remaining punctuation
            if not part:
                continue
            if part.isdigit() and part.isascii():
                words.extend(_number_to_words(int(part)).split())
            else:
                words.append(part)
    return words


# --------------------------------------------------------------------------- alignment


def _word_credit(target: str, heard: str, threshold: float) -> float:
    """0..1 credit for hearing ``heard`` where ``target`` was expected."""
    if target == heard:
        return 1.0
    g = _HOMOPHONES.get(target)
    if g is not None and g == _HOMOPHONES.get(heard):
        return 1.0
    sim = _similarity(target, heard)
    return sim if sim >= threshold else 0.0


@dataclass
class _Pair:
    target: Optional[str]  # None = extra heard word
    heard: Optional[str]  # None = missed word
    credit: float


def align(target: list[str], heard: list[str], threshold: float) -> list[_Pair]:
    """Edit-distance alignment. A match costs ``1 - credit``; a substitution,
    insertion or deletion costs 1. Ties prefer pairing words up (so a wrong word
    is reported as "heard X instead", not as one miss plus one extra)."""
    n, m = len(target), len(heard)
    credit = [[_word_credit(t, h, threshold) for h in heard] for t in target]
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = credit[i - 1][j - 1]
            diag = cost[i - 1][j - 1] + (1.0 - c if c > 0 else 1.0)
            cost[i][j] = min(diag, cost[i - 1][j] + 1.0, cost[i][j - 1] + 1.0)

    pairs: list[_Pair] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            c = credit[i - 1][j - 1]
            diag = cost[i - 1][j - 1] + (1.0 - c if c > 0 else 1.0)
            if abs(cost[i][j] - diag) < 1e-9:
                pairs.append(_Pair(target[i - 1], heard[j - 1], c))
                i, j = i - 1, j - 1
                continue
        if i > 0 and abs(cost[i][j] - (cost[i - 1][j] + 1.0)) < 1e-9:
            pairs.append(_Pair(target[i - 1], None, 0.0))
            i -= 1
        else:
            pairs.append(_Pair(None, heard[j - 1], 0.0))
            j -= 1
    pairs.reverse()
    return pairs


# --------------------------------------------------------------------------- result


@dataclass
class PronunciationResult:
    status: str
    score: Optional[int] = None  # 0-100, None unless status == "scored"
    max_score: int = MAX_SCORE
    transcript: str = ""
    confidence: float = 0.0
    matched_words: list[str] = field(default_factory=list)
    missed_words: list[str] = field(default_factory=list)
    needs_improvement: list[dict[str, Optional[str]]] = field(default_factory=list)
    feedback: str = ""
    feedback_code: str = ""
    score_basis: str = SCORE_BASIS
    provisional: bool = True

    @property
    def scored(self) -> bool:
        return self.status == STATUS_SCORED

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict for API responses."""
        return {
            "score": self.score,
            "max_score": self.max_score,
            "status": self.status,
            "transcript": self.transcript,
            "confidence": self.confidence,
            "matched_words": list(self.matched_words),
            "missed_words": list(self.missed_words),
            "needs_improvement": [dict(x) for x in self.needs_improvement],
            "feedback": self.feedback,
            "feedback_code": self.feedback_code,
            "score_basis": self.score_basis,
            "provisional": self.provisional,
        }


# Plain-English, encouraging messages. Not diagnostic: the score does not know *why*
# a word was not recognised.
_FEEDBACK = {
    "great": "Great job! That was clear.",
    "good": "Good try! Most of it was clear. Try the highlighted words again.",
    "keep_going": "Nice effort. Listen once more, then try again slowly.",
    "try_again": "Let's try again. Listen first, then say it slowly.",
    "low_confidence": "We couldn't hear that clearly enough to score it. Try again in a quiet place.",
    "unclear_transcript": "We couldn't make out the words. Try again a little closer to the phone.",
    "invalid_target": "There is no word to practise here.",
    Status.EMPTY_AUDIO.value: "We didn't get any sound. Please try recording again.",
    Status.INVALID_AUDIO.value: "We couldn't play that recording. Please try again.",
    Status.TOO_SHORT.value: "That was very short. Please say the whole word or sentence.",
    Status.TOO_LONG.value: "That recording was too long. Please record just the word or sentence.",
    Status.NO_SPEECH.value: "We didn't hear any speech. Please try again, a little louder.",
    Status.MODEL_ERROR.value: "Something went wrong on our side. Please try again in a moment.",
}


def _unscored(code: str, status: str, **kw: Any) -> PronunciationResult:
    return PronunciationResult(status=status, feedback=_FEEDBACK[code], feedback_code=code, **kw)


def _band(score: int) -> str:
    if score >= GREAT_AT:
        return "great"
    if score >= GOOD_AT:
        return "good"
    if score >= KEEP_GOING_AT:
        return "keep_going"
    return "try_again"


# --------------------------------------------------------------------------- main

Transcriber = Callable[..., TranscriptionResult]


def score_pronunciation(
    audio: AudioInput,
    target_text: str,
    *,
    transcriber: Optional[Transcriber] = None,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    min_confidence: float = MIN_CONFIDENCE,
) -> PronunciationResult:
    """Score one spoken attempt against ``target_text``. Never raises.

    Args:
        audio: path, bytes or binary file object (anything ``ml.speech.transcribe`` takes).
        target_text: the word or sentence the learner was trying to say.
        transcriber: ``f(audio, language) -> TranscriptionResult``. Defaults to
            ``ml.speech.transcribe``; tests pass a fake so no model is needed.
        fuzzy_threshold: 0-1 string similarity at which a heard word counts as the
            target word.
        min_confidence: ASR confidence below which no score is given.
    """
    target = normalize(target_text)
    if not target:
        return _unscored("invalid_target", STATUS_UNAVAILABLE)

    fn = transcriber or _default_transcribe
    try:
        tr = fn(audio, language=LANGUAGE)
    except Exception:  # transcribe() raises only on a wrong argument type (our bug), not bad audio
        return _unscored(Status.MODEL_ERROR.value, Status.MODEL_ERROR.value)

    status = getattr(tr.status, "value", tr.status)
    if status != Status.OK.value:
        code = status if status in _FEEDBACK else Status.MODEL_ERROR.value
        return _unscored(code, status)

    text = tr.text or ""
    conf = float(tr.confidence or 0.0)
    heard = normalize(text)
    if not heard:
        return _unscored("unclear_transcript", STATUS_UNAVAILABLE, transcript=text, confidence=conf)
    if conf < min_confidence:
        return _unscored("low_confidence", STATUS_UNAVAILABLE, transcript=text, confidence=conf)

    pairs = align(target, heard, fuzzy_threshold)
    matched: list[str] = []
    missed: list[str] = []
    issues: list[dict[str, Optional[str]]] = []
    credit = 0.0
    extras = 0
    for p in pairs:
        if p.target is None:
            extras += 1
            issues.append({"word": None, "heard": p.heard, "issue": ISSUE_EXTRA})
        elif p.credit > 0:
            matched.append(p.target)
            credit += p.credit
            if p.heard != p.target and p.credit < 1.0:
                issues.append({"word": p.target, "heard": p.heard, "issue": ISSUE_CLOSE})
        else:
            missed.append(p.target)
            issue = ISSUE_MISSED if p.heard is None else ISSUE_DIFFERENT
            issues.append({"word": p.target, "heard": p.heard, "issue": issue})

    score = round(MAX_SCORE * credit / (len(target) + EXTRA_WORD_WEIGHT * extras))
    score = max(0, min(MAX_SCORE, score))
    code = _band(score)
    return PronunciationResult(
        status=STATUS_SCORED, score=score, transcript=text, confidence=round(conf, 4),
        matched_words=matched, missed_words=missed, needs_improvement=issues,
        feedback=_FEEDBACK[code], feedback_code=code,
    )
