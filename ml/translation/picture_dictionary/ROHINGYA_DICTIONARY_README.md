# Rohingya picture dictionary and phrasebook

Load `rohingya_dictionary_200_words_and_phrases.json` as UTF-8 JSON. This package is separate from `ml/translation/data` because its schema differs from the datasets loaded by the translator and backend seeder; it is not imported by those components automatically.

- `words`: exactly 200 vocabulary entries, including lexical compounds such as “sore throat.”
- `phrases`: 110 phrase entries, additional to the 200 vocabulary entries.
- `entry_type`: `word` or `phrase`.
- `part_of_speech`: the source classification where available; some vocabulary classifications are provisional. `phrase` is reserved for the phrases section. Vocabulary terms originally classified as phrases use `lexical expression`. Unknown classifications are `null`.
- `rohingya`: the preserved source spelling, including diacritics and transcription marks.
- `english`: the English meaning. `english_meanings` preserves multiple meanings where entries were consolidated.
- `definition`: a short English explanation of the meaning.
- `image_url`: a portable relative path to a matching PNG, or `null` where an image is pending.
- `english_audio`: a relative path and metadata for the English text-to-speech placeholder; the audio is machine-generated and unvalidated.
- `source_references` and `source_entries`: published references and original file/entry pointers.

## File naming

All entries use `rohingya_001` through `rohingya_310`. Available pictures use the same stem:

```text
rohingya_dictionary_200_words_and_phrases.json
Images_2/
  rohingya_001.png
  ...
  rohingya_303.png
```

Vocabulary uses IDs 001–200. Phrases use IDs 201–310. Seven new phrases (304–310) do not yet have images. Keep the JSON beside `Images_2`, or resolve its relative image paths against your app's asset root. All delivered PNGs are 1024 × 1024 pixels. Existing original image filenames were preserved; the unified names are additional copies.

English audio files are in `Audio/`, named `rohingya_001_audio_en_tts_placeholder.mp3` through `rohingya_310_audio_en_tts_placeholder.mp3`. The ID matches the catalog entry and, where present, its image. `audio_manifest.json` records the text, voice, and source details. These are English machine-generated placeholders; Rohingya recordings are not included.

To reproduce missing audio, install the dependencies and model described in `ml/tts/README.md`, then from the repository root run:

```sh
python -m ml.tts generate --lexicon ml/translation/picture_dictionary/rohingya_dictionary_200_words_and_phrases.json --limit 310 --out ml/translation/picture_dictionary/Audio --manifest ml/translation/picture_dictionary/audio_manifest.json --audio-label
```

The generator does not overwrite existing files. The app and translation loader do not automatically import this package.

## Selection and review

The catalog retains 98 original vocabulary entries: the untranslated “Greet” was excluded, and `gom` (“Good” / “Fine”) was consolidated into one entry. It adds 38 vocabulary items from the supplied topic collections and 64 concrete entries checked against the Rohingya Language Foundation's English–Rohingya dictionary. Source spelling variations are preserved rather than automatically converted.

The phrases section combines the supplied topic and phrasebook collections. Seven previously excluded entries from David’s source files are now included to preserve the full source list. They include model-fallback drafts and conflicting translations and are marked for review; phrase_038 also has a different wording for an existing Goodbye entry. Earlier 30- and 40-entry greetings files overlap the main lexicon and do not increase the count.

Every entry remains pending native-speaker review. Published attestation and imported review claims do not establish independently verified translation accuracy. Editorial English definitions and generated pictures are learning aids, not translation evidence. Some relationship or abstract vocabulary pictures illustrate context rather than uniquely identifying the meaning by themselves.

`rohingya_dictionary_provenance.json` preserves original entry metadata, source notes and attributions, and the picture prompt set. Some original metadata contains unverified examples; use the main catalog for import. Preserve applicable source attribution and licensing information when redistributing the material.

The completed asset package reuses 98 existing pictures and adds 205 pictures made with the built-in image generation tool. The 103 phrase pictures are separate from the 200 vocabulary pictures; the seven newly added phrases have no pictures yet.

`rohingya_dictionary_validation.json` records structural and file checks. These checks do not replace linguistic review.
