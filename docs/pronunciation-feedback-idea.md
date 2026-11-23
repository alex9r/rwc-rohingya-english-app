# Idea: "Was this score fair?" feedback

**Proposal only. Nothing is built; collect nothing until the consent questions below are answered.**

## The idea

After a score, the app asks one question: **"Was this score fair?" 👍 / 👎**. The answer is stored with the
clip ID, transcript and score, giving a steady stream of real-world evidence from the people using it.

## Why

The scorer is an uncalibrated ASR match (`provisional: true`). Two failures are invisible to tests:

- **Too harsh:** a clear attempt Whisper misheard (👎 on a low score).
- **Too generous:** Whisper "autocorrects" an accent, so a hard-to-understand attempt scores high (👎 on a high score).

Thumbs are cheap, take no effort and work in any language.

## What is stored

| Field | Notes |
|---|---|
| `clip_id` | opaque id, not a filename containing a name |
| `word_id` / `target_text` | what was practised |
| `transcript`, `confidence`, `score`, `status`, `feedback_code` | exactly what the app showed |
| `fair` | `true` (👍) / `false` (👎) |
| `scorer_version`, `created_at` | which thresholds produced it, when |
| `user_id` | pseudonymous only, and only if progress tracking already needs it |

Audio is stored only with a separate opt-in (below).

## How it feeds calibration

An input to Hari's evaluation, not a replacement:

1. Hari's WER evaluation on recordings with known transcripts sets the first thresholds.
2. Thumbs are a **check**: per score band, what share say "fair"? Many 👎 on high scores means too
   generous; many on low scores means too harsh.
3. 👎 rows are the shortlist for a qualified speaker to listen to (only where audio is kept with consent).
   That judgement, not the votes, decides any threshold change.
4. Votes are noisy, and learners can't judge their own accent, so they **never** retrain or set
   thresholds automatically.

## Consent and privacy

- The app must say what happens, in plain language, translated: "Tell us if this score was fair. We keep
  your answer to improve the app."
- **Answer-only is low risk; answer plus audio is personal data** and needs its own explicit opt-in, a way
  to withdraw, and deletion.
- Transcripts are personal too (they hold what a learner said): same retention and access rules.
- Minimise: no names or contact details, pseudonymous ids, a set retention period.
- Participation is optional and must never affect access, progress or Centre services.
- A 👎 is not evidence of good or bad pronunciation and is never shown back to the learner as a judgement.
- The Centre and TPMs agree who holds the data, where, and whether ethics review is needed (same questions
  as the [collection plan](pronunciation-recording-collection-plan.md)).

## Rough build (if approved)

App: two buttons and one `POST /api/pronunciation/feedback` (Nikiel). Backend: a table, no audio unless
opted in. Analysis: a notebook of 👍/👎 rate per score band (Hari).
