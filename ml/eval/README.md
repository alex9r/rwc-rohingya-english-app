# ml/eval — transcription evaluation suite (Rohingya + English)

Scores any transcriber against **verified transcripts**: word-level wrong / missing / extra
words, WER, CER, and a per-phrase verdict (`correct`, `missing_words`, `incorrect_words`,
`extra_words`, `mixed_errors`, `no_output`). Breakdowns by speaker, noise, pace, or any
manifest field. No model is needed to run the tests; no third-party dependencies.

This is the framework. The Whisper model/config benchmark and the choice of production
model are Hari's; this suite is what that benchmark can run on Rohingya.

## Status

- Built and unit-tested on hand-written strings (`python -m pytest ml/eval`).
- **No Rohingya audio exists in the repo yet.** `data/CLEAR_Gamayun_rhg-eng_5k` is text only
  (5,000 sentence pairs). So there are no Rohingya WER numbers, and none are quoted here.

## Pipeline

```bash
# 1. draw a recording-prompt list (read-only on the kit; same seed = same set for everyone)
python -m ml.eval prompts data/CLEAR_Gamayun_rhg-eng_5k prompts.jsonl -n 100 --max-words 8

# 2. as recordings arrive: fill audio, speaker_id (pseudonymous), noise/pace; a Rohingya
#    speaker checks each reference and their ID goes in verified_by
python -m ml.eval validate manifest.jsonl

# 3. evaluate (the proxy language is recorded in the report)
python -m ml.eval run manifest.jsonl --language bn --model small --out report
```

Manifest fields are documented at the top of `manifest.py`. Rows with no `verified_by` are
rejected unless `--allow-unverified`. Fields that identify a person (`name`, `email`, ...)
are rejected. Audio and real manifests stay out of git (see the recording-collection plan).

## Decisions that matter

- **Script mismatch.** The kit writes Rohingya in romanised Latin. Whisper has no Rohingya, so
  a `bn`/`ur` proxy will usually answer in Bengali/Arabic script. Comparing across scripts gives
  a meaningless ~100% WER, so those clips are flagged `script_mismatch` and left out of WER.
  Real Rohingya numbers need either references in the script the ASR emits or a transliteration
  step, which is a team decision.
- **Orthography marks.** `'`, `*` and `-` are part of the kit's spelling. The default is strict;
  `--fold-marks` ignores them so annotator variation isn't scored as error. Report both.
- **Failed transcriptions** count as all words missing (standard WER) and are listed separately.
- WER is micro-averaged (total errors / total reference words).

## Credits

Prompts come from CLEAR Global's Gamayun Rohingya kit (CC BY 4.0), whose English source
sentences are from Tatoeba (check its per-sentence licence before redistributing).
