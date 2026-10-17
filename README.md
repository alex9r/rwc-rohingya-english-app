# Rohingya Reception House: Rohingya–English Learning App

An AI-enabled, voice-first app that helps Rohingya newcomers build practical spoken English for work and everyday life in Canada. Built with the Rohingya community by a [WAT.ai](https://wat.ai) project team at the University of Waterloo, in partnership with the Rohingya Welcome Centre and The Reception House.

> **Status:** Early development (Term 1). The UI mockup and data schema come first, followed by the backend and the speech and translation experiments.

## Why this project exists

Many Rohingya newcomers face real barriers to learning English. The problem is not only vocabulary. Most language and translation tools assume users can read, type, and navigate complex interfaces. Through our partnership with the Rohingya Welcome Centre and earlier community hackathon work, we found that an **oral-first, low-text, scenario-based** approach fits this community best.

Rohingya is also a low-resource language, with limited speech and translation support in existing tools. So this project is both a product and a research effort. We rely on community-validated language resources and test carefully what current AI models can and cannot do before the app promises it.

## What we're building

**Core features**
- Rohingya ↔ English vocabulary and translation, starting with the top 100 essential words
- Picture-based, searchable dictionary built from community-provided linguistic resources
- Audio playback for words and phrases, plus saved words and phrases
- Scenario practice such as job interviews, workplace conversations, healthcare visits, transportation, and grocery shopping
- Pronunciation feedback using speech recognition and text-to-speech
- AI-assisted translation and conversational practice, with a "not sure" signal when confidence is low

**Possible future features**
- Personalized exercises and progress tracking
- Offline vocabulary and audio
- Improved Rohingya speech recognition through additional training data
- WhatsApp integration

## Design principles

1. **Voice and images first.** Minimal reading and typing.
2. **Community-validated content.** Vocabulary, translations, and scenarios are reviewed by the Rohingya Welcome Centre and language experts before they count as done.
3. **Honest about AI limits.** We use existing pretrained models and APIs and measure their accuracy on Rohingya data rather than assuming it.
4. **Small, demoable milestones.** Early and frequent community feedback.

## Repository structure

```
rwc-rohingya-english-app/
├── app/        # Expo / React Native mobile app (TypeScript)
├── backend/    # FastAPI service and PostgreSQL models
├── ml/         # Speech and translation experiments, evaluation scripts, notebooks
├── data/       # Shared lexicon (lexicon.json) and schema
└── docs/       # Scope, decisions, meeting notes, FLIGHT plan
```

## Tech stack

| Area | Tools |
|---|---|
| UI/UX | Figma, FigJam |
| Mobile | React Native, Expo, TypeScript |
| Backend | Python, FastAPI, PostgreSQL |
| Storage | Firebase |
| Speech-to-text | OpenAI Whisper |
| LLMs | OpenAI, Google Gemini, Anthropic Claude (under evaluation) |
| Text-to-speech | ElevenLabs, Google TTS (under evaluation) |
| Speech research | PyTorch, Hugging Face Transformers, SpeechBrain, librosa |
| Tooling | GitHub Actions, Docker, Expo EAS, Kaggle, Jupyter, pandas |

## Data and resources

- Rohingya dictionary and pronunciations provided by the Rohingya Welcome Centre
- [Rohingya Language](https://rohingyalanguage.org/) resources and Rohingya Language Book orthography standard
- TWB Parallel Sentence Kits, Rohingya (about 5k pairs)
- IOM Rohingya Dictionary
- Voice of America Rohingya ASR dataset (pronunciations need validation because of dialect variation)
- [Tatoeba](https://tatoeba.org/en/) for English example sentences

## Lexicon format

Each vocabulary entry in `data/lexicon.json` follows this shape (the schema is still being finalized):

```json
{
  "rohingya": "",
  "english": "",
  "pos": "noun",
  "plural_form": "",
  "example": { "rohingya": "", "english": "" },
  "category": "family",
  "image_prompt": "",
  "audio_url": ""
}
```

## Getting started

> Setup instructions will be added once the first mockup is merged. The goal is that a teammate can run the app in under 10 minutes.

```bash
git clone https://github.com/<org>/rwc-rohingya-english-app.git
cd rwc-rohingya-english-app/app
npm install
npx expo start
```

## Roadmap (8 months)

| Phase | Focus |
|---|---|
| Months 1–2 | Team onboarding, UI mockup, community feedback, backend proof of concept, first 3 translated words in the app |
| Month 3 | Top 50 words, term-end showcase, in-person demo with the Welcome Centre |
| Months 5–6 | Apply community feedback, expand vocabulary and a second scenario area (for example healthcare or employment), final Welcome Centre demo session |
| Month 7 | End-of-term showcase, user manual, optional research paper submission |
| Month 8 | Documentation and public deliverables |

## Team

Built by WAT.ai student members across full-stack/mobile development and ML/speech research, led by technical project managers Mansi Katarey and Alexandra Roszczenko.

## Contributing

- Work on a branch, open a pull request, and get one review before merging.
- Each task should have a named owner and a clear "done means" line.
- Content added to `data/` (words, translations, audio) must be marked **unvalidated** until the Welcome Centre has reviewed it.
- Missed a deliverable? Tell the TPMs in Discord.

## Acknowledgments

Thank you to the Rohingya Welcome Centre and The Reception House for their partnership, community connections, and language resources, and to WAT.ai for project support.

## License

TBD. Confirm with the TPMs and partners before adding one, especially for language data and audio.