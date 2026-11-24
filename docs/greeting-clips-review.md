# Review of the 40 greeting clips

*Mohammed (speech), Nov 23, 2026*

This review covers the 40 audio clips in `data/audio`, listed in `data/audio_manifest.json`. They are Luna's English TTS placeholders for the Rohingya Greetings Lexicon (Kokoro, voice `af_heart`). Each clip went through `ml.speech.transcribe()` with Whisper `small`, language `en`, on a laptop CPU. Each transcript was compared with the clip's expected word using Luna's `ml.eval` WER.

**These are machine-made English words, not Rohingya speech.** The review checks the clips and how confidence behaves on single words. It does not calibrate the Rohingya thresholds, which still need Luna's checked Rohingya clips.

## Summary

| | |
|---|---|
| Clips that transcribed (status `ok`) | 40 / 40 |
| Heard as the expected word | 35 / 40 |
| Confidence | 0.29 – 0.61, median 0.46 |
| Asked to repeat at the current line (LOW 0.50) | 31 |
| ...of which were heard right anyway | **28** |
| Clip length | 0.66 – 1.09 s |
| Processing time per clip | median 1.3 s (2.7 s for the first, which includes loading the model) |

## What it means

1. **The clips are usable.** Every clip decodes, none is silent or too short, and 35 of 40 transcribe as their word.
2. **The 0.50 low line is too strict for single words.** Whisper is never very sure about one isolated word, even clean, correct audio. At 0.50 the app would ask users to repeat 28 words it had heard right. Run on these clips, `calibrate.py` recommends a high line of 0.40 and no low line, since none of these clips is truly bad. The cutoffs stay at 0.70 / 0.50 until Luna's Rohingya clips are in; Rohingya through a proxy language will score lower than English. Calibration should use word-length clips like the app's, not long sentences.
3. **Single words get misheard in predictable ways.** If a screen compares what was heard with the expected word, it should accept these:
   - homophones: *Meet* heard as "meat"
   - an extra word Whisper adds: *Name* heard as "The name", *Speak* as "and speak", *Thank* as "Thank you"

## To check by ear

| Clip | Expected | Heard | Why |
|---|---|---|---|
| greeting_020 | Greet | Agreed | most likely an unclear TTS clip; worth a listen |
| greeting_015 | Name | The name | a word Whisper often adds; the audio is probably fine |
| greeting_024 | Speak | and speak | same |
| greeting_022 | Thank | Thank you | Whisper completing the phrase; the audio is probably fine |
| greeting_019 | Meet | meat | homophone; the audio is fine |

## All 40 clips

| # | Expected | Heard | Confidence | Action | Right? |
|---|---|---|---|---|---|
| 001 | Hello | Hello. | 0.45 | ask_repeat | yes |
| 002 | Goodbye | Goodbye. | 0.46 | ask_repeat | yes |
| 003 | Welcome | Welcome! | 0.42 | ask_repeat | yes |
| 004 | Thanks | Thanks. | 0.53 | confirm | yes |
| 005 | Please | Please | 0.51 | confirm | yes |
| 006 | Sorry | Sorry. | 0.43 | ask_repeat | yes |
| 007 | Yes | Yes. | 0.55 | confirm | yes |
| 008 | No | No. | 0.51 | confirm | yes |
| 009 | Okay | Okay. | 0.45 | ask_repeat | yes |
| 010 | Good | Good. | 0.55 | confirm | yes |
| 011 | Fine | Fine. | 0.36 | ask_repeat | yes |
| 012 | Happy | Happy! | 0.48 | ask_repeat | yes |
| 013 | Nice | Nice. | 0.45 | ask_repeat | yes |
| 014 | Well | Well. | 0.50 | ask_repeat | yes |
| 015 | Name | The name. | 0.38 | ask_repeat | **no** |
| 016 | Friend | friend. | 0.34 | ask_repeat | yes |
| 017 | Family | family. | 0.29 | ask_repeat | yes |
| 018 | Guest | Guest. | 0.46 | ask_repeat | yes |
| 019 | Meet | meat. | 0.42 | ask_repeat | **no** |
| 020 | Greet | Agreed. | 0.61 | confirm | **no** |
| 021 | Introduce | Introduce. | 0.48 | ask_repeat | yes |
| 022 | Thank | Thank you. | 0.51 | confirm | **no** |
| 023 | Help | Help. | 0.54 | confirm | yes |
| 024 | Speak | and speak. | 0.34 | ask_repeat | **no** |
| 025 | Listen | Listen. | 0.40 | ask_repeat | yes |
| 026 | Understand | Understand. | 0.48 | ask_repeat | yes |
| 027 | Today | today | 0.49 | ask_repeat | yes |
| 028 | Tomorrow | tomorrow. | 0.49 | ask_repeat | yes |
| 029 | Morning | morning. | 0.42 | ask_repeat | yes |
| 030 | Evening | Evening | 0.45 | ask_repeat | yes |
| 031 | Excuse me | Excuse me. | 0.54 | confirm | yes |
| 032 | Polite | polite | 0.45 | ask_repeat | yes |
| 033 | Respect | Respect. | 0.45 | ask_repeat | yes |
| 034 | Kind | kind. | 0.44 | ask_repeat | yes |
| 035 | Introduction | Introduction. | 0.50 | ask_repeat | yes |
| 036 | Conversation | Conversation. | 0.48 | ask_repeat | yes |
| 037 | Invitation | Invitation. | 0.44 | ask_repeat | yes |
| 038 | Visitor | Visitor | 0.47 | ask_repeat | yes |
| 039 | Grateful | Grateful. | 0.44 | ask_repeat | yes |
| 040 | Peace | Peace. | 0.47 | ask_repeat | yes |

## Re-running it

```bash
python -m ml.speech.run_clips data/audio --language en --model small --out greetings40.csv
# add a 'wer' column (Luna's ml.eval score_clip against the manifest's text), then:
python -m ml.speech.calibrate greetings40_with_wer.csv
```
