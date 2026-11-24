# Rohingya evaluation clips: how they were collected and how consent was given

Luna, 23 Nov 2026. Part of the Rohingya test suite built with [`ml/eval`](../ml/eval/README.md).

**Status: waiting for a reply.** We have asked the Rohingya Welcome Centre for a Rohingya
speaker to transcribe an 80-clip pack. No transcripts have come back, so there are no
Rohingya results yet. The `[to fill]` items below are filled in when they do.

## Source of the audio

The clips are not recordings we made. They come from Voice of America Rohingya radio news,
as published in the Hugging Face dataset
[`freococo/rohingya_asr_audio`](https://huggingface.co/datasets/freococo/rohingya_asr_audio)
(about 357 hours, split into 6–15 second chunks, no transcripts, no speaker labels).

- **Licence:** the dataset card lists PDDL (public domain), on the basis that VOA output is
  US government work (17 U.S.C. § 105). We have not verified that independently. The card
  warns that some chunks may include music or third-party clips.
- **No recording at the Welcome Centre.** Nobody from the Centre was recorded for this.
- **Speakers:** broadcasters and guests on public radio. They are unknown to us and were not
  asked for consent, which is why we use only published public-domain broadcasts and make no
  attempt to identify or analyse speakers. Every clip carries the same label (`voa_broadcast`).
- **Content:** news, which may cover conflict. The transcriber is told they can skip any clip.

## How the 80 clips were chosen

Reproducible with `python -m ml.eval pack <shard.tar> <out_dir>`; the settings below are the defaults.

- Shard `rohingya-00000.tar` only (10,000 clips from 56 broadcasts). The other 13 shards were not used.
- Skip the first 5 clips of each broadcast, because openings carry an English station ident.
- Keep clips of 5–12 seconds; at most 4 per broadcast; random seed 11.
- Result: 80 clips from 44 broadcast dates, 673 seconds (about 11 minutes) in total.
- Files are renamed `voa_001.mp3` to `voa_080.mp3`. The link from each clip back to its
  broadcast is kept in `_private_source_map.csv`, which is not shared with the transcriber.

Selection did not check for music or English by listening. The transcriber marks those
clips "unusable", and the target is at least 50 usable clips out of the 80.

## What the transcriber was asked to do

Write what is said in Latin letters (Rohingyalish) in their usual spelling, without
translating; mark unusable clips with a reason (music, English, unclear, other); flag words
they are unsure about; and describe any spelling conventions they followed. The sheet and
its instructions are built by `ml/eval/pack.py`.

## How consent was given

Consent here means the **transcriber's** agreement to help, not the speakers' (see above).

| | |
|---|---|
| What was asked | A Rohingya speaker writes out up to 80 short clips; at least 50 needed. |
| What they were told | The clips are public VOA radio and nobody at the Centre was recorded; only an ID (for example `T01`) is stored, not their name, unless they want credit; they can skip clips and stop at any time; the transcripts are compared with speech-recognition output to measure errors. |
| How agreement is recorded | `[to fill]` The Centre's email reply, kept by the project leads. |
| Intended use of the transcripts | `[to fill]` Project leads to confirm whether they will be released openly. Say so to the transcriber before they start. |
| Payment | `[to fill]` Project leads to decide. |
| Storage | The sheet holds an ID and transcripts, no names. Audio and source map stay outside git. |

## Limits

- One transcriber per clip, so references are one native speaker's reading, not double-checked.
  A second person checking a subset would measure agreement. This needs more volunteers.
- Broadcast news is professional speech, not learner speech. Results measure Rohingya
  recognition in general, not Welcome Centre learners.
- Rohingya spelling is not standardised. Reports should show strict and lenient spelling.

## When transcripts arrive

```bash
python -m ml.eval ingest transcription_sheet.xlsx audio manifest.jsonl --source-map _private_source_map.csv
python -m ml.eval validate manifest.jsonl
python -m ml.eval run manifest.jsonl --language bn --model small --out report   # and --fold-marks
```

Run the same manifest through each model being compared and keep the proxy language in the
report. Do not quote any Rohingya number until this has been run on real transcripts.
