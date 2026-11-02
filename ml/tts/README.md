# ml/tts: English placeholder audio

Generates **labelled placeholder** audio for the English side of lexicon words, so the app
has something to play on the Word Detail screen (`audio_url`) and the pronunciation
endpoint has a `reference_audio_url`. It is machine speech, not a native speaker, and
every file and manifest entry says so.

Owner: Luna (speech). Lexicon content and naming: Marcus. Playback: Linxi.

## Rules this module follows

- **English only.** Rohingya has no TTS and nothing here reads Rohingya text; the
  Bengali (or any other) voice is never used as a stand-in. The tests check that only
  the English word reaches the engine.
- **Always labelled.** File name `<word_id>_en_tts_placeholder.mp3`, plus an entry in
  `data/audio_manifest.json` with `kind: "tts_placeholder"`, `validated: false`, `engine`,
  `voice`, `date`.
- **Never overwrites.** Existing files are skipped; manifest entries of any other kind
  (such as `native_speaker`) are kept as they are.
- **Never edits the lexicon.** It only reads it. A proposed `audio_url` change is below,
  for Marcus.
- **No keys, no paid services.** The default engine is local. Keys for any future
  engine come from environment variables only.

## Setup and use

```bash
pip install -r ml/tts/requirements.txt
python -m ml.tts fetch-model          # one-off, ~120 MB, public download, no key

python -m ml.tts generate --hero      # the 3 hero words
python -m ml.tts generate             # up to 40 words from the lexicon (--limit N)
python -m ml.tts generate --ids greeting_001 greeting_005
```

The output reports what it did (`created`, `skipped (already exists)`, `FAILED`, and
warnings), and running it again changes nothing. Options: `--lexicon PATH` (read only),
`--out DIR` (default `data/audio`), `--manifest PATH` (default `data/audio_manifest.json`),
`--backend NAME`, `--voice NAME`.

Model files go to `~/.cache/rwc-tts/` (override with `RWC_KOKORO_MODEL`,
`RWC_KOKORO_VOICES` or `RWC_TTS_CACHE`). They are not committed.

**Hero words.** The repo does not define them. `HERO_IDS` in `generate.py` is a placeholder
choice (Hello, Thanks, Goodbye: `greeting_001`, `greeting_004`, `greeting_002`), to be
confirmed by the TPMs.

**Lexicon source.** `data/lexicon.json` does not exist yet. Until it does, the default
`--lexicon` is the stand-in `ml/translation/data/rohingya_greetings_30.json`. The loader
reads `entries[].id` with `english_meaning.word` or `english`. Point `--lexicon` at
Marcus's file when it lands.

## Regenerating

Delete the file(s) you want redone (and optionally their manifest entry) and rerun. Files
are git-ignored (`data/audio/.gitignore`), so a fresh clone gets the same audio by running
`generate`. The manifest is committed. Note that Kokoro output is not guaranteed
bit-identical across versions or machines; the manifest records the engine, voice and date.

## Swapping the backend

A backend is any object with `name`, `voice`, `license_note` and
`synthesize(text) -> (float32 mono samples, sample_rate)`:

```python
from ml.tts import register_backend
register_backend("my_engine", lambda **opts: MyEngine(**opts))
# python -m ml.tts generate --backend my_engine
```

Set a default with `RWC_TTS_BACKEND`. The README lists ElevenLabs and Google TTS as under
evaluation; neither is implemented here because both are paid or key-gated. Adding one
needs the team's go-ahead; its key would come from an environment variable, and its
terms on storing and redistributing output would need checking first (see licensing).

## Licensing and terms of the default voice

| Part | Licence | Notes |
|---|---|---|
| Kokoro-82M weights (`af_heart` voice) | Apache-2.0 (model card, `hexgrad/Kokoro-82M`) | The card says the weights "can be deployed anywhere", including commercially. |
| `kokoro-onnx` runtime | MIT | |
| `espeakng-loader` / espeak-ng | GPL-3.0 | Used as a tool at generation time only; the audio it helps make is not a GPL work, and nothing GPL ships in the app. |
| Training data | permissive audio, per the card | The card lists two CC BY sets used in training (Koniwa `tnc`, SIWIS). **Credit Kokoro and these sets in the app's credits.** |

Checked on 2026-11-02 against the model card; **this is not legal advice**, and the voice
`af_heart` has no separate licence statement beyond the model's. The TPMs/Welcome Centre
should confirm before audio ships to users.

**Why not the macOS `say` command or other system voices:** Apple's licence for its
built-in voices (checked from published licence text for older macOS versions; I did not
find the current text) allows personal, non-commercial use and forbids publishing or
redistributing the voices' output, even for non-profit or public sharing. That rules it
out for audio that ships in an app or sits in the repo.

## From placeholder to native speaker

Placeholders are temporary. When a native speaker's recording has been reviewed by the
Welcome Centre ([collection plan](../../docs/pronunciation-recording-collection-plan.md)):

1. Add the recording under `data/audio/` with its own name (for example
   `<word_id>_native.m4a`) and a manifest entry with `kind: "native_speaker"`,
   `validated: true` and the reviewer/speaker pseudonym. The generator never touches it.
2. Point the lexicon's audio field at the native file (Marcus) and keep the placeholder
   in the manifest or delete it.
3. The pronunciation API (`docs/pronunciation-api-contract.md` on the scorer PR) reports
   `reference_audio_kind: "native_speaker"` instead of `"tts_placeholder"` for that word.
   The backend can derive the kind from the manifest entry it served.

## Proposed lexicon change (for Marcus: not applied)

`audio_pronunciation` in the draft schema looks like the *Rohingya* pronunciation, so
English TTS should not go there. Proposal: a separate `english_audio` object per entry
(shown for the three hero words, against a copy of the stand-in file; `audio_url` in the
README shape could carry the same path):

```diff
--- a/data/lexicon.json (draft)
+++ b/data/lexicon.json (draft)
@@ -46,5 +46,10 @@
       "image": null,
       "different_forms": [],
-      "validation_status": "dictionary_attested_pending_native_review"
+      "validation_status": "dictionary_attested_pending_native_review",
+      "english_audio": {
+        "path": "data/audio/greeting_001_en_tts_placeholder.mp3",
+        "kind": "tts_placeholder",
+        "validated": false
+      }
     },
     {
@@ -79,5 +84,10 @@
       "image": null,
       "different_forms": [],
-      "validation_status": "translation_pending_source_verification"
+      "validation_status": "translation_pending_source_verification",
+      "english_audio": {
+        "path": "data/audio/greeting_002_en_tts_placeholder.mp3",
+        "kind": "tts_placeholder",
+        "validated": false
+      }
     },
     {
@@ -148,5 +158,10 @@
       "image": null,
       "different_forms": [],
-      "validation_status": "dictionary_attested_pending_native_review"
+      "validation_status": "dictionary_attested_pending_native_review",
+      "english_audio": {
+        "path": "data/audio/greeting_004_en_tts_placeholder.mp3",
+        "kind": "tts_placeholder",
+        "validated": false
+      }
     },
     {
```

## Tests

```bash
python -m pytest ml/tts -q
```

Offline, using a fake backend (no model download). They cover file naming, manifest
fields, mp3 playability, idempotence, never overwriting, keeping `native_speaker`
entries, one failure not stopping the batch, unsafe ids, English-only text, and
backend registration.

## Quality check on the default voice

I transcribed the 30 greeting words with Whisper `base` as a rough check that the audio
says the word. 28 came back exactly as the word; two were ambiguous as single words:
"Greet" was heard as "Agreed." and "Thank" as "Thank you." None of the three hero words
was affected. This is a quick intelligibility check, not a listening review, and placeholders remain
unvalidated.
