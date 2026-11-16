# Whisper benchmark: model and config recommendation

Hari, 9 Nov 2026. Follows [`whisper-evaluation.md`](whisper-evaluation.md).
Scripts: [`benchmark.py`](../ml/evaluation/benchmark.py) (latency, configs),
[`wer_benchmark.py`](../ml/evaluation/wer_benchmark.py) (accuracy).

## Recommendation

**`small`, beam 1, no context conditioning, loaded at startup and kept warm.**

| Model | WER | Per call | Cold start |
|---|---|---|---|
| tiny | 4.3% | 0.5 s | 0.4 s |
| base | 4.3% | 0.7 s | 0.6 s |
| **small** | **1.8%** | **1.8 s** | **1.9 s** |
| medium | 1.4% | 7.6 s | 21.6 s |

`small` halves base's error rate for one extra second. `medium` buys 0.4 points
for 4x the compute and a 21 s cold start. `large-v3` is out at roughly 10x real
time, though it is the only size that handles Rohingya at all.

`base` is a fine fallback if latency becomes a complaint.

## Method

No recording exists whose correct transcript is known, which blocks every
accuracy number. TTS gets around that: we pick the sentence, so the reference is
exact. Sentences come from the team's phrase set
(`ml/translation/data/rohingya_phrases_38.json`), 12 phrases x 6 macOS voices,
72 clips. Standard WER, punctuation and case normalised away.

**Synthetic speech is clean and fluent, so absolute numbers are optimistic.**
Relative comparisons hold, and that is what a model choice rests on.

`tiny` and `base` scored identical WER, probably an artifact of clean audio.

Latency is measured with English forced. Decode time scales with output length,
so a model that loops looks far slower than it is: forced to Bengali, `small`
times at 5.5 s a call against 1.8 s in English, because the loop fills a whole
decoding window. Benchmark in a language the model can handle.

## Accent

`small`, by voice locale:

| en_US | en_IE | en_AU | en_GB | en_IN | en_ZA |
|---|---|---|---|---|---|
| 0.0% | 0.0% | 1.2% | 2.4% | 2.4% | 4.9% |

Non-US accents degrade. But 12 clips per locale is a few word errors, not a
sample, and a TTS voice is a stylised accent rather than second-language speech.
Rohingya-accented English will be harder than this. Read it as evidence that
accent matters, not as a prediction.

## Noise and speaking rate

`small`, against known text:

| clean | 20 dB | 10 dB | 5 dB | 0.8x | 1.2x | 1.5x |
|---|---|---|---|---|---|---|
| 1.8% | 3.3% | 4.7% | 10.8% | 1.6% | 1.8% | 1.2% |

**Speaking rate does not matter.** Flat from 0.8x to 1.5x. A learner speaking
slowly costs nothing.

**Noise does.** 6x the error rate at 5 dB, and a learner with a TV on sits in the
5 to 15 dB range. The app should check input level and ask for a re-record rather
than scoring through it. "I could not hear that clearly" beats a bad score caused
by a kettle.

## Decoding config

`small`, forced English, five VOA clips:

| Config | RTF | Agreement |
|---|---|---|
| beam 1, no context | 0.17 | baseline |
| beam 5, no context | 0.86 | 0.43 |
| beam 1, context on | 0.17 | 1.00 |

Beam 5 costs 5x and produces different text, not better text. Context
conditioning changes nothing.

## Worth testing

Perturbing audio slightly and decoding twice makes output move a lot when the
model is guessing, agreement 0.37 to 0.68 on audio it could not handle. Could work
as a rejection signal: decode twice, disagreement means don't trust it. Catches
confident nonsense, which log-prob misses. Mohammed, maybe worth a look.

## Gap

All of this is synthetic speech. What is missing is real learners, with the
hesitation and first-language interference no TTS voice produces.

Fix: record speakers saying known English words from the lexicon. The transcript
is known because we choose the word, so no transcription step and no orthography
decision. 5 to 10 speakers x 20 words gives 100 to 200 clips, enough to redo every
number here on real speech and calibrate the scorer's thresholds.

That is the shared dataset deliverable, and it blocks the rest of my accuracy work
and Luna's calibration.
