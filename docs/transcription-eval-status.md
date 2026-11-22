# Transcription evaluation: status, first run, and what's missing

## Summary

- The evaluation framework is built and runs end to end on real audio and real model output.
- The only real run so far is **English** (below). It checks the pipeline; it is not a benchmark.
- **There is no standardized Rohingya test suite yet**, because there are no verified Rohingya transcripts. This document says what is needed to build one.

## Run 1: `transcribe()` on English with known text

**Purpose:** confirm the framework works on real model output, using audio whose correct text is known.

| | |
|---|---|
| Audio | 50 clips from Mozilla Common Voice Scripted Speech 27.0 English (CC0), the same clips as the pronunciation smoke test |
| Reference | The sentence each contributor was prompted to read |
| Transcriber | `ml.speech.transcribe()`, faster-whisper `base`, `language="en"`, via `ml.eval.runner` |
| Matching | Strict: `'`, `*`, `-` are kept; case and sentence punctuation ignored |

### Overall

| Metric | Result |
|---|---|
| WER | 8.4% (22 wrong, 1 missing, 5 extra, of 335 reference words) |
| CER | 3.7% |
| Exact-phrase accuracy | 76% (38 of 50 clips) |
| Phrase verdicts | 38 correct, 7 `incorrect_words`, 5 `mixed_errors`, 0 `missing_words`, 0 `extra_words`, 0 `no_output` |

### By accent label (from the dataset)

| Accent label | Clips | WER | CER | Phrase accuracy |
|---|---|---|---|---|
| Canadian English | 8 | 1.9% | 0.4% | 87.5% |
| England English | 8 | 17.9% | 8.2% | 62.5% |
| Filipino | 2 | 14.3% | 5.3% | 50.0% |
| Hong Kong English | 8 | 2.2% | 0.4% | 87.5% |
| India and South Asia | 8 | 10.0% | 4.8% | 62.5% |
| Scottish English | 8 | 11.3% | 4.7% | 75.0% |
| Southern African | 2 | 10.0% | 5.8% | 50.0% |
| United States English | 6 | 0.0% | 0.0% | 100.0% |

### Example errors the framework reports

| Clip | Verdict | Detail |
|---|---|---|
| cv27-1009475 | incorrect_words | `fishes` heard as `fishers` |
| cv27-10324151 | incorrect_words | `the` → `a`, `hall` → `hole` |
| cv27-100316 | incorrect_words | `thing's` → `things` (a strict-spelling difference) |
| cv27-100881 | mixed_errors | `boy` missing; `preferred` → `biopreferred` |
| cv27-100891 | mixed_errors | 4 wrong words, 1 extra |

## What was not done: the Rohingya test suite

The task is a standardized suite of Rohingya audio with verified transcripts. It could not be built because:

1. **No verified transcripts exist.** The VOA Rohingya broadcast corpus (`freococo/rohingya_asr_audio`, public domain, about 357 hours) is audio only.
2. **The Gamayun kit is text only.** `data/CLEAR_Gamayun_rhg-eng_5k` has 5,000 sentence pairs and no audio.

## What is needed

| Need | Who | Notes |
|---|---|---|
| Transcripts of 50–100 VOA clips by a Rohingya speaker | Team or the translation team | Clips chosen to be short, speech-only (no music), spread across broadcast dates. Record the checker's pseudonymous ID in `verified_by`. |
| Decision on transcript script | Team | Latin Rohingyalish (matches the Gamayun kit) is the proposal. Whisper forced to `bn` tends to answer in Bengali script, so those clips would be flagged `script_mismatch` and excluded from WER until there is a transliteration step or Bengali-script references. |
| Decision on MMS | Team | `facebook/mms-1b-all` has an `rhg` adapter but is CC BY-NC 4.0 (non-commercial), needs PyTorch and transformers, and is a 3.9 GB download. |
| Models to compare | Hari | e.g. Whisper `small` / `large-v3` with a proxy language, and MMS `rhg`. |
| Build the manifest | Luna | `python -m ml.eval validate` then `run`. |

## Plan

1. Pick the clips and prepare a transcription sheet.
2. A Rohingya speaker transcribes them; the manifest is validated.
3. Run Whisper (proxy language) and MMS `rhg` on the same clips.
4. Run `ml.eval` for word-level wrong, missing and extra words, WER, CER and phrase verdicts by model.
