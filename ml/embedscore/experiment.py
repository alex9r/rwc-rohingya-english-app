"""Compare the embedding distance with the ASR-match scorer on the English smoke-test clips.

Question: does embedding distance carry information the transcript-matching scorer misses,
and is it worth building on? What this CAN show is limited, because no human-rated
learner speech exists. It runs three checks on the 75 smoke-test clips (Tatoeba + Common Voice):

  A. Different-sentence test. Each clip against its own sentence and against the other 74
     sentences. Does the true sentence come out best? (top-1 and pairwise AUC)
  B. One-word-swap test. Each clip against its own sentence and against the same sentence
     with its longest word replaced by a word from another sentence. Does the measure
     notice one wrong word? This is the closest stand-in for a mispronounced word.
  C. Agreement with ASR errors. Spearman correlation between the embedding distance to the
     true sentence and the per-clip WER of `transcribe()` (via ml.eval).

Reference audio is synthetic speech from macOS `say` (voice Samantha), generated locally and
never committed (Apple's licence does not allow redistributing it). Needs macOS.

    python -m ml.embedscore.experiment --out /tmp/embed_run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import subprocess
from pathlib import Path

import numpy as np

from ml.eval.metrics import score_clip
from ml.pronunciation.scorer import score_pronunciation
from ml.speech.transcribe import load_audio, transcribe

from .dtw import dtw_distance
from .embed import Wav2Vec2Embedder

LAYERS = (4, 8, 12)
PRON = Path(__file__).resolve().parents[1] / "pronunciation"
SETS = (("smoke_manifest.csv", "smoke_clips", "tatoeba"), ("smoke_manifest_cv.csv", "smoke_clips_cv", "common_voice"))


def load_clips() -> list[dict]:
    rows = []
    for manifest, folder, name in SETS:
        with open(PRON / manifest, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                path = PRON / folder / r["file"]
                if path.is_file():
                    rows.append({"id": r["clip_id"], "path": path, "target": r["target_text"],
                                 "set": name, "accent": r.get("accent_label", "")})
    return rows


def swap_word(sentence: str, others: list[str], rng: random.Random) -> str | None:
    """Replace the sentence's longest word with a (different) word taken from another sentence."""
    words = sentence.split()
    if len(words) < 2:
        return None
    idx = max(range(len(words)), key=lambda i: len(words[i].strip(".,!?\"'")))
    old = words[idx].strip(".,!?\"'").lower()
    pool = [w.strip(".,!?\"'") for s in others for w in s.split()]
    pool = [w for w in pool if len(w) >= 3 and w.lower() != old and w.lower() not in sentence.lower()]
    if not pool:
        return None
    words[idx] = rng.choice(pool)
    return " ".join(words)


def say(text: str, out_dir: Path, voice: str = "Samantha") -> Path:
    out = out_dir / (hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16] + ".aiff")
    if not out.exists():
        subprocess.run(["say", "-v", voice, "-o", str(out), text], check=True)
    return out


def ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    for v in np.unique(x):                     # average ranks over ties
        m = x == v
        r[m] = r[m].mean()
    return r


def spearman(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def auc_less(pos: float, negs: list[float]) -> float:
    """Share of negatives that `pos` beats (lower is better); ties count half."""
    n = np.asarray(negs)
    return float(((pos < n).sum() + 0.5 * (pos == n).sum()) / len(n))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="base", help="faster-whisper size for transcribe()")
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    refs_dir = a.out / "refs"
    refs_dir.mkdir(exist_ok=True)

    clips = load_clips()
    n = len(clips)
    rng = random.Random(a.seed)
    targets = [c["target"] for c in clips]
    swapped = [swap_word(t, [x for j, x in enumerate(targets) if j != i], rng) for i, t in enumerate(targets)]
    print(f"{n} clips; {sum(s is not None for s in swapped)} with a word-swap reference")

    # --- embeddings (clips, every sentence reference, every swapped reference)
    emb = Wav2Vec2Embedder()

    def embed_file(path: Path) -> dict[int, np.ndarray]:
        return emb(np.asarray(load_audio(str(path))), LAYERS)

    clip_emb = [embed_file(c["path"]) for c in clips]
    ref_emb = [embed_file(say(t, refs_dir)) for t in targets]
    swap_emb = [embed_file(say(s, refs_dir)) if s else None for s in swapped]
    print("embedded")

    # --- ASR side: transcribe each clip once; reuse for every target
    results = {str(c["path"]): transcribe(str(c["path"]), language="en", model_size=a.model) for c in clips}
    cached = lambda audio, language=None: results[str(audio)]  # noqa: E731
    asr_own, asr_wer = [], []
    asr_scores = np.zeros((n, n))
    for i, c in enumerate(clips):
        for j in range(n):
            r = score_pronunciation(str(c["path"]), targets[j], transcriber=cached)
            asr_scores[i, j] = r.score if r.score is not None else np.nan
        tr = results[str(c["path"])]
        asr_wer.append(score_clip(c["id"], c["target"], tr.text if tr.ok else "").wer)
    asr_own = np.diag(asr_scores)
    scored = ~np.isnan(asr_own)

    out: dict = {"clips": n, "asr_model": a.model, "layers": {}}
    for layer in LAYERS:
        D = np.array([[dtw_distance(clip_emb[i][layer], ref_emb[j][layer]) for j in range(n)] for i in range(n)])
        own = np.diag(D)
        top1 = float(np.mean(D.argmin(axis=1) == np.arange(n)))
        auc_a = float(np.mean([auc_less(D[i, i], np.delete(D[i], i)) for i in range(n)]))
        pairs = [(i, d) for i, s in enumerate(swap_emb) if s is not None
                 for d in [dtw_distance(clip_emb[i][layer], s[layer])]]
        auc_b = float(np.mean([auc_less(D[i, i], [d]) for i, d in pairs]))
        out["layers"][layer] = {
            "A_top1": top1, "A_auc": auc_a, "B_auc": auc_b,
            "own_distance_mean": float(own.mean()),
            "own_distance_by_set": {s: float(np.mean([own[i] for i, c in enumerate(clips) if c["set"] == s]))
                                    for s in {c["set"] for c in clips}},
            "spearman_distance_vs_asr_wer": spearman(own, asr_wer),
        }

    # ASR scorer on the same tests (score is higher-is-better, NaN where scoring was withheld)
    a_auc, b_auc, top1 = [], [], []
    for i in range(n):
        if np.isnan(asr_own[i]):
            continue
        negs = np.delete(asr_scores[i], i)
        negs = negs[~np.isnan(negs)]
        a_auc.append(auc_less(-asr_own[i], list(-negs)))
        top1.append(float(asr_own[i] > np.nanmax(negs)) if len(negs) else 0.0)
    for i, s in enumerate(swapped):
        if s is None or np.isnan(asr_own[i]):
            continue
        r = score_pronunciation(str(clips[i]["path"]), s, transcriber=cached)
        if r.score is not None:
            b_auc.append(auc_less(-asr_own[i], [-r.score]))
    out["asr_scorer"] = {"scored": int(scored.sum()), "withheld": int((~scored).sum()),
                         "A_top1_strict": float(np.mean(top1)), "A_auc": float(np.mean(a_auc)),
                         "B_auc": float(np.mean(b_auc)) if b_auc else None, "B_n": len(b_auc)}
    out["asr_wer_mean"] = float(np.mean([w for w in asr_wer if w is not None]))
    out["clips_with_asr_errors"] = int(sum(1 for w in asr_wer if w))
    with open(a.out / "results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
