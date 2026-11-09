# Whisper on Rohingya audio: evaluation

Hari, 2 Nov 2026. Data: `freococo/rohingya_asr_audio` (VOA Rohingya broadcasts),
shard 0. Scripts in [`ml/evaluation`](../ml/evaluation/README.md).

## Scope

Asked for WER and common failures, trying Bengali and English settings since
Whisper has no Rohingya.

**WER is not computable.** The corpus has no transcripts, and no reference
Rohingya speech data exists anywhere I could find. What follows is failure modes
plus two clips whose content I could verify independently.

20 clips, one per broadcast, fixed seed, 5 s minimum, openings skipped. Three
models, each decoded with Bengali forced, English forced, and auto. Greedy at
temperature 0. English and Bengali TTS controls on every run.

## small and medium are unusable, and uninterpretable

Forced Bengali collapsed into a repeated syllable on 20/20 clips in both,
compression ratios 4 to 21 against Whisper's own threshold of 2.4.

These runs say nothing about Rohingya. The same collapse happens on clean English
and on real Bengali, so it is the model failing on Bengali. English transcribed
perfectly, so the install is fine.

Run a control in whatever language you force, before reading anything into the
output.

## large-v3 works, partially

Loops dropped to 2/20 on forced Bengali and 0/20 on forced English. The Bengali
control passed, so the results mean something.

**The same sounds come back in three scripts.** Clip 007606:

| Pass | Output |
|---|---|
| forced en | Sonasandhya Shildiheen ... Tihavishya Jomachildiheen ... Hathi Guris |
| forced bn | সুনাসান্দিয়া স্ছিল্দিহিন আর তিহা ভুষা জমা স্ছিল্দিহিন দাহাতিগুরি |
| auto (Devanagari) | सुनासान्दियाच्छिल्दिहिन आर तिहाँ भुष्याजमाच्छिल्दिहिन |

Three independent decodings converging on one phonetic string is not
hallucination. Same on clip 008400 (Garaja / গরাজা) and 007346, where English,
Bengali and Turkish passes all land on *siyasi*, politics.

**One clip checks out semantically.** Clip 009428, broadcast 7 Nov 2022. Forced
English: "the cup 27 meeting ... the relationship between losses and". Forced
Bengali: `COP27` plus নুকসান (*nuksan*, loss). COP27 opened 6 November with loss
and damage as its headline item. Right acronym, right topic, right date, two
languages.

**The station ident transcribes exactly.** Clip 000001 returns "Voice of America,
Washington." verbatim, log-prob -0.303. Note the ident is spoken in English, so
this verifies English transcription in this corpus, not Rohingya.

## Numbers

| | small | medium | large-v3 |
|---|---|---|---|
| forced bn, loops | 20/20 | 20/20 | 2/20 |
| forced en, loops | n/a | n/a | 0/20 |
| detect top-1 = bn | 7/20 | 7/20 | 7/20 |
| detect confidence, median | 0.40 | 0.45 | 0.57 |
| Bengali control | failed | failed | passed |

Language detection is unreliable at every size. large-v3 called one clip Spanish
at 0.40 and another Turkish at 0.57, then produced fluent Spanish and Turkish for
them. It called the clean English ident "English" at 0.352, with Japanese second.
Nothing should trust `detect_language` on this audio.

## For the transcription function

Average log-prob separates languages better than Whisper's detector. On a
forced-English pass, genuine English scores -0.218 and -0.20; every Rohingya clip
sits between -1.0 and -1.4. No overlap.

Through `segment_confidence` in `ml/speech`, roughly
`exp(avg_logprob) x (1 - no_speech_prob)`:

- Rohingya forced to English: 0.25 to 0.37
- Actual English: about 0.82

So `LOW_CONFIDENCE = 0.5` rejects non-English cleanly. But the gap to Luna's
withheld Common Voice clips (0.40 to 0.49, real English with hard words) is thin,
so one number carries two failures: wrong language and hard vocabulary. Two bands
would be better. Below 0.40 unusable; 0.40 to 0.50 prompt a retry rather than
withholding silently.

One caveat on log-prob: it only separates languages while the model is not
looping. A repeated token is trivially predictable, so the small and medium loops
score -0.17 to -0.24, better than real English. Pair log-prob with the
compression-ratio check, which `segment_confidence` already does.

## MMS is the obvious alternative

Meta's MMS has a Rohingya adapter, `facebook/mms-1b-all` with `rhg`, plus
`facebook/mms-tts-rhg` for synthesis. Luna ran it on this corpus and it
transcribed the station ident as `gásof amérika wacíngthon`, a phonetic
Rohingyalish spelling of the same English words. Both models heard the same thing
and spelled it in whichever script they were forced into.

MMS should be evaluated against large-v3. Her setup is a Colab T4 behind ngrok,
fine for a demo and not for the Centre, so hosting is unowned.

## One thing about the corpus

Clip 007902 transcribes as "Let's start with enhance. Of the three words we are
studying today, enhance is the least common." That is VOA Learning English inside
the Rohingya broadcast, and clip 005490 looks similar. There is English teaching
material in here aimed at Rohingya listeners. Someone should check how much.

## Limitations

- 2 of 14 shards profiled; I assume the rest match
- 20 clips, enough for failure modes, not accuracy
- No speaker has checked any transcript
- large-v3 output is Bengali script, a fourth spelling system on top of the three
  already in our sources
- large-v3 is ~2 min a clip on an M2, not shippable

Raw output in `~/Desktop/voa_rhg/`: `whisper_x0_sample20/`, `_medium/`,
`_largev3/`, `whisper_x0_finish/`. Each has `results.json` and `transcripts.txt`.
