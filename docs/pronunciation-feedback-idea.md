# Idea: "Was this score fair?" feedback

**Status: proposal only. Nothing is built, and nothing should be collected until the consent
questions below are answered.**

## The idea

After a learner sees a pronunciation score, the app asks one question with two buttons:
**"Was this score fair?" 👍 / 👎**. The answer is stored with the clip ID, the transcript and
the score. That gives us a steady trickle of real-world evidence about when the scorer is
too harsh or too generous, from the people who actually use it.

## Why it is useful

The scorer is an uncalibrated ASR match (`score_basis: "asr_match"`, `provisional: true`).
Two things go wrong that we cannot see from tests:

- **Too harsh:** a clear attempt that Whisper misheard, scoring low (👎 on a low score).
- **Too generous:** Whisper "autocorrects" accented speech, scoring high on an attempt a
  listener would find hard to understand (👎 on a high score).

A thumbs signal is cheap, needs no extra effort from the learner, and is easy to give in
any language.

## What would be stored

One row per answer:

| Field | Notes |
|---|---|
| `clip_id` | an opaque id for the recording (not a filename with a name in it) |
| `word_id` / `target_text` | what was being practised |
| `transcript`, `confidence`, `score`, `status`, `feedback_code` | exactly what the app showed |
| `fair` | `true` (👍) or `false` (👎) |
| `scorer_version` | which thresholds/model produced the score |
| `created_at` | timestamp |
| `user_id` | only a pseudonymous id, and only if progress tracking already needs it |

The audio itself is stored only if the learner has separately agreed to that (below).

## How it feeds calibration

This is input to Hari's evaluation, not a replacement for it.

1. Hari's WER evaluation, done on recordings with known transcripts, sets the first
   thresholds (`MIN_CONFIDENCE`, fuzzy threshold, score bands).
2. Thumbs data is then used as a **check**: for each score band, what share of answers
   say "fair"? If many 👎 sit on high scores, the scorer is too generous there; if many on
   low scores, too harsh.
3. Rows with 👎 are the shortlist for a qualified speaker to listen to (only where audio
   is stored with consent). Their judgement, not the learners' votes, decides any threshold
   change.
4. Votes are noisy (people tap casually, and a learner cannot judge their own accent), so
   they are **never used to retrain or set thresholds automatically**.

## Consent and privacy

- **The app must say what happens.** A short, plain-language, translated notice: "Tell us
  if this score was fair. We keep your answer to improve the app."
- **Answer-only vs answer-plus-audio are different.** Keeping a thumbs answer with the
  transcript and score is low risk. Keeping the voice recording is personal data and
  needs an explicit, separate opt-in ("Can we keep this recording to improve the app?"),
  with a way to withdraw and delete it.
- **Transcripts are personal too**: they contain what a learner said. Same retention and
  access rules as other project data.
- **Minimise:** no real names or contact details attached; pseudonymous ids only; set a
  retention period.
- **Children and vulnerable users:** the audience is newcomers, some potentially in
  precarious situations. Participation must be optional and must never affect their
  access, progress or anything from the Centre.
- **Don't over-interpret:** a 👎 is not evidence the learner pronounced badly or well.
  It must not be shown back to the learner as a judgement.
- **Governance:** the Welcome Centre and the TPMs should agree on who holds this data,
  where it is stored, and whether a research-ethics review is needed, the same questions
  as the [recording collection plan](pronunciation-recording-collection-plan.md).

## Rough build (if approved)

- App: two buttons under the score; one `POST /api/pronunciation/feedback` call with the
  fields above (Nikiel).
- Backend: a table; no audio unless the opt-in is set.
- Analysis: a small notebook comparing 👍/👎 rates per score band (Hari).

## Open questions

1. Do we want this before the first evaluation is done, or only after?
2. Opt-in for audio retention: does it ship with the app, or is it a later addition?
3. Where is the data stored, and for how long?
4. Does the translated wording of the question work in Rohingya ("fair" is easy to
   mistranslate)? The Centre should check it.
