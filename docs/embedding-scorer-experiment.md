# Embedding-based pronunciation comparison: first experiment

Luna, 23 Nov 2026. Code: [`ml/embedscore`](../ml/embedscore/README.md). **Experimental; the app
still uses the ASR-match scorer.**

## Question

Could a speech-to-speech comparison (embeddings of the learner's audio against embeddings of a
reference reading) replace or add to the ASR-match scorer? This run checks whether it behaves
sensibly. It cannot say whether it measures pronunciation well, because the repo has no
human-rated learner speech.

## Setup

- **Learner clips:** the 75 English smoke-test clips (25 Tatoeba, 50 Common Voice), the same ones
  as [`pronunciation-test-notes.md`](pronunciation-test-notes.md).
- **Reference audio:** one synthetic voice (macOS `say`, Samantha), generated locally for each
  clip's sentence and not committed.
- **Embedding scorer:** wav2vec 2.0 base hidden states, DTW with cosine cost
  ([how it works](../ml/embedscore/README.md)). Layers 4, 8 and 12 were chosen before running;
  8 is the default. Nothing was tuned afterwards.
- **ASR scorer:** `ml.pronunciation.score_pronunciation` on `ml.speech.transcribe()`
  (Whisper `base`, `language="en"`), each clip transcribed once.

## Results

| | Embedding L4 | Embedding **L8** | Embedding L12 | ASR-match |
|---|---|---|---|---|
| A. Own sentence vs the other 74: top-1 | 98.7% | **100%** | 70.7% | 100% (70 clips) |
| A. Pairwise AUC | 0.999 | **1.000** | 0.943 | 1.000 |
| B. Own sentence vs one-word swap: AUC | 0.987 | **0.973** | 0.867 | 0.986 (70 clips) |
| C. Spearman, distance vs per-clip WER | 0.09 | **0.10** | -0.06 | n/a |

- **A** asks whether the true sentence is the best match. **B** swaps a clip's longest word for a
  word from another sentence and asks whether the true sentence still wins; it is the nearest
  stand-in we have for one mispronounced word.
- ASR-match withheld 5 of the 75 clips (confidence below 0.5), so its columns cover 70. The
  embedding scorer has no confidence check and returned a distance for all 75.
- 17 of the 75 clips had at least one word error from `transcribe()`; the mean per-clip WER was 6.8%.
- Mean own-sentence distance at layer 8 was 0.52 for Common Voice and 0.37 for Tatoeba.

## What this shows

- It works: at layer 8 it picks the right sentence for all 75 clips and notices a swapped word
  almost as well as the ASR-match scorer (0.97 vs 0.99; different clip counts).
- Layer matters a lot: layer 12 is much worse. A default chosen in advance happened to do well;
  with one voice and 75 clips this is not evidence that layer 8 is the right choice.
- Distance does not track the ASR's mistakes (Spearman about 0.1). That could mean it measures
  something the transcript misses, or something irrelevant such as speaker and recording
  differences. This run cannot tell which.
- Raw distances differ by recording source (0.52 vs 0.37), so a distance is not comparable
  across recording conditions without calibration.

## What this does not show

- Whether a smaller distance means better pronunciation. That needs recordings rated by people.
- Anything about Rohingya-accented English: no such recordings exist.
- Whether it beats the ASR scorer: both are at the ceiling on these easy tests (A and B).
- Cost and speed. I did not measure latency or hosting needs, and it adds PyTorch and a
  360 MB model to the stack.
- Robustness to a different reference voice: only one was used.

## Recommendation

Keep the ASR-match scorer in the app. Keep this as an experiment until there are rated
learner recordings (the consent-based plan in
[`pronunciation-recording-collection-plan.md`](pronunciation-recording-collection-plan.md)).
Then compare both scorers against human ratings, and test minimal pairs and several reference voices.

## Rerun

```bash
pip install -r ml/embedscore/requirements.txt
python -m ml.embedscore.experiment --out /tmp/embed_run   # macOS; needs the local smoke clips
```
