# App (Expo + TypeScript)
## Run

Requires Node (current LTS) and, for a phone, the **Expo Go** app (must support Expo SDK 58).

```bash
cd app
npm install
npx expo start        # press w (web), i (iOS sim), a (Android), or scan the QR in Expo Go
```

| Script | Purpose |
|---|---|
| `npm run lint` | ESLint (expo config + Prettier) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run format` | Prettier |

**Phone can't connect?** Phone and computer must share a Wi-Fi network that allows device-to-device traffic. Try `npx expo start --tunnel` or a phone hotspot.

## Screens

| Tab / route | What it does |
|---|---|
| **Speak** `speak` | Tap mic, speak, tap to stop. Shows translation, confidence badge ("Not sure" under 50%), reads English aloud, replays and saves the recording. Swap direction (Rohingya ↔ English). Camera button translates text from a photo (OCR mocked). |
| **Words** `words` | Dictionary as **Cards** or **Table**. Search by English or Rohingyalish, filter by topic or **Saved**, voice search via mic. Each word: image, audio, Rohingya/English text, save, best score. Tap a word to practice. |
| **Word practice** `word/[id]` | Hear the English word (normal or slow), say it, get a score, tips and replay. Score is a placeholder, flagged "not validated". |
| **Scenario** `scenario/…` | Pick a topic → pick a scenario → chat-style practice with a mic and placeholder feedback after each reply. Finishing marks it complete. |
| **Learn** `learn` | Overall progress, "Up next" word, saved/scenario/score tiles, per-topic progress that links into Words. |

Topics: Healthcare, Education, Housing, Greetings, Transportation, Employment, Family.

## Structure

```
app/
├── src/
│   ├── app/            # Expo Router routes (file = screen)
│   │   ├── (tabs)/     #   speak, words, learn, scenario/ (index, category/[categoryId], [id])
│   │   └── word/[id]   #   pronunciation practice
│   ├── api/            # types.ts, mockData.ts, client.ts (mock API; swap for fetch() later)
│   ├── components/     # shared UI (MicButton, WordCard, FloatingTabBar, …)
│   ├── hooks/          # useRecorder, usePlayAudio
│   ├── state/          # AppState: saved words + progress
│   ├── theme/          # colors, fonts, spacing, shadows
│   └── utils/
├── app.json            # Expo config + permission strings
└── eslint.config.js
```

## Notes

- **Mock persistence:** saved words and progress are stored on-device (AsyncStorage) by `api/client.ts`, standing in for `GET/POST /api/progress`. Clear app/site data to reset.
- **Swapping in the backend:** replace function bodies in `src/api/client.ts`; screens only call `api.*`.