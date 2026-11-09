# Whisper on Rohingya audio: evaluation

Hari, 2 Nov 2026. Data: `freococo/rohingya_asr_audio` (VOA Rohingya broadcasts), shard 0.

## What this is

I was asked for word error rate and common failures, trying Bengali and English
settings since Whisper has no Rohingya.

WER is not computable here. The corpus has no transcripts, so there is nothing to
score against. That is the finding, not a gap in the work: there is no reference
Rohingya speech data anywhere that I could find. What follows is failure modes,
plus two accuracy checks on clips where I could independently verify the content.

Sample: 20 clips, one from each of 20 different broadcasts, fixed seed, 5 seconds
minimum, skipping broadcast openings. Three models (small, medium, large-v3), each
clip decoded with Bengali forced, English forced, and auto-detected language,
greedy at temperature 0. English and Bengali TTS controls on every run.

## Small and medium produce nothing usable

Forced Bengali collapsed into a repeated syllable on 20 of 20 clips in both models.
Compression ratios 4 to 21, against Whisper's own degeneracy threshold of 2.4.

These runs cannot be interpreted. The same collapse happens when I force Bengali on
clean English speech and on real Bengali speech, so it is the model failing on
Bengali, not on Rohingya. English transcribed perfectly in the same setup, so the
install is fine.

If anyone repeats this, run a control in the language you are forcing before
reading anything into the results.

## large-v3 is a different story

Loops dropped from 20 of 20 to 2 of 20 on forced Bengali, and 0 of 20 on forced
English. The Bengali control stopped collapsing, so these results mean something.

Three pieces of evidence that it is transcribing real speech rather than
hallucinating.

**The same sounds come back in three scripts.** Clip 007606 decoded into Latin,
Bengali and Devanagari gives the same sound sequence each time:

| Pass | Output |
|---|---|
| forced en | Sonasandhya Shildiheen ... Tihavishya Jomachildiheen ... Hathi Guris |
| forced bn | সুনাসান্দিয়া স্ছিল্দিহিন আর তিহা ভুষা জমা স্ছিল্দিহিন দাহাতিগুরি |
| auto (Devanagari) | सुनासान्दियाच्छिल्दिहिन आर तिहाँ भुष्याजमाच्छिल्दिहिन |

Three independent decodings converging on one phonetic string is not something a
hallucinating model does. Same pattern on clip 008400 (Garaja / গরাজা) and clip
007346, where the English, Bengali and Turkish passes all land on *siyasi*,
politics.

**One clip checks out semantically.** Clip 009428, broadcast 7 Nov 2022. Forced
English gives "the cup 27 meeting ... the relationship between losses and". Forced
Bengali gives the literal string `COP27` alongside নুকসান (*nuksan*, loss). COP27
opened on 6 November and loss and damage was its headline agenda item. Right
acronym, right topic, right date, in two languages.

**The station ident transcribes exactly.** Clip 000001 is the broadcast opening. I
know what it says because I listened to it. Forced English returns "Voice of
America, Washington." verbatim, log-prob -0.303.

Worth being precise about that last one: the ident is spoken in English, so it
verifies English transcription in this corpus, not Rohingya.

## What the numbers say

| | small | medium | large-v3 |
|---|---|---|---|
| forced bn, loops | 20/20 | 20/20 | 2/20 |
| forced en, loops | n/a | n/a | 0/20 |
| detect top-1 = bn | 7/20 | 7/20 | 7/20 |
| detect confidence, median | 0.40 | 0.45 | 0.57 |
| Bengali control | failed | failed | passed |

Language detection is unreliable at every model size. large-v3 called one clip
Spanish at 0.40 and another Turkish at 0.57, then produced fluent Spanish and
Turkish for them on the auto pass. It also called the clean English ident "English"
at only 0.352, with Japanese second. Nothing should trust `detect_language` on this
audio.

## The useful finding for the transcription function

Average log-probability separates languages better than Whisper's own detector.

On a forced-English pass, the two clips that genuinely are English score -0.218 and
-0.20. Every Rohingya clip lands between -1.0 and -1.4, median -1.04. No overlap.

That maps onto `segment_confidence` in `ml/speech`, which is roughly
`exp(avg_logprob) × (1 - no_speech_prob)`:

- Rohingya speech forced to English: confidence about 0.25 to 0.37
- Actual English in the same corpus: about 0.82

So `LOW_CONFIDENCE = 0.5` does reject non-English cleanly. The gap to Luna's
withheld Common Voice clips (0.40 to 0.49, real English with hard words) is thin
though, which means one number is carrying two different failures: wrong language
and hard vocabulary. Worth two bands rather than one cutoff. Below 0.40, unusable.
Between 0.40 and 0.50, probably English the model found hard, so prompt a retry
instead of withholding silently.

## Correction to my earlier writeup

I said no usable Rohingya ASR exists. That is too strong, and I was only testing
Whisper.

Meta's MMS has an actual Rohingya adapter, `facebook/mms-1b-all` with `rhg`, plus
`facebook/mms-tts-rhg` for synthesis. Luna ran it on this same corpus in her
earlier project and it transcribed the station ident as `gásof amérika wacíngthon`,
a phonetic Rohingyalish spelling of the English words. Both models heard the same
thing and each spelled it in the script they were forced into.

MMS should be evaluated properly against large-v3. Her setup runs on a Colab T4
through ngrok, which is fine for a demo and will not survive contact with the
Centre, so hosting is an open question nobody has picked up.

## One thing worth knowing about the corpus

Clip 007902 transcribes as "Let's start with enhance. Of the three words we are
studying today, enhance is the least common." That is VOA Learning English content
inside the Rohingya broadcast. Clip 005490 looks similar. There is English teaching
material in this corpus aimed at Rohingya listeners, which is close enough to what
this app does that someone should look at how much of it there is.

## Limitations

- Two of 14 shards profiled. I assume the rest match.
- Twenty clips. Enough for failure modes, not for accuracy.
- No speaker has checked any transcript. The verification above rests on two clips
  where I could check content independently.
- large-v3 output is Bengali script, which matches none of the orthographies the
  team is using. That is a fourth spelling system on top of the three already in
  our sources.
- `base` and `small` were not tested on CPU for latency. Everything here is
  large-v3 on an M2, roughly 2 minutes a clip, which is not shippable.

## Files

Scripts and raw output are in `~/Desktop/voa_rhg/`: `whisper_x0_sample20/` (small),
`_medium/`, `_largev3/`, and `whisper_x0_finish/` (forced English and the ident
test). Each has `results.json` with per-segment log-probs and `transcripts.txt`.
Happy to commit these if useful.
