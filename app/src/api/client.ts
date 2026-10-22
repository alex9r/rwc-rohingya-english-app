import AsyncStorage from '@react-native-async-storage/async-storage';
import { categories, mockOcrText, mockTranslations, scenarios, words } from './mockData';
import type {
  Category,
  Direction,
  PronunciationResult,
  ProgressSummary,
  ProgressUpdate,
  Scenario,
  ScenarioFeedback,
  TranslateResult,
  Word,
} from './types';

/**
 * Mock API client. Mirrors the shape of the planned backend but reads from
 * mockData.ts. Swap the bodies for fetch() calls once the backend exists.
 *
 * Progress and saved words live in a tiny "mock database" persisted to
 * AsyncStorage, standing in for POST/GET /api/progress and a saved-words endpoint
 * (which the backend draft doesn't have yet).
 */
const delay = <T>(value: T, ms = 300): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

interface Db {
  saved: string[];
  wordScores: Record<string, number>;
  latestScore: number | null;
  completedScenarios: string[];
}

const DB_KEY = 'rwc.mock.db.v1';
const emptyDb = (): Db => ({
  saved: [],
  wordScores: {},
  latestScore: null,
  completedScenarios: [],
});

let dbPromise: Promise<Db> | null = null;
const loadDb = (): Promise<Db> =>
  (dbPromise ??= AsyncStorage.getItem(DB_KEY)
    .then((raw): Db => (raw ? { ...emptyDb(), ...JSON.parse(raw) } : emptyDb()))
    .catch(emptyDb));
const persist = (db: Db) => AsyncStorage.setItem(DB_KEY, JSON.stringify(db)).catch(() => {});

function summarize(db: Db): ProgressSummary {
  const practiced = new Set(Object.keys(db.wordScores));
  return {
    wordsPracticed: practiced.size,
    wordsTotal: words.length,
    scenariosCompleted: db.completedScenarios.length,
    scenariosTotal: scenarios.length,
    latestScore: db.latestScore,
    wordScores: db.wordScores,
    completedScenarioIds: db.completedScenarios,
    categories: categories.map((c) => ({
      categoryId: c.id,
      name: c.name,
      wordsPracticed: words.filter((x) => x.categoryId === c.id && practiced.has(x.id)).length,
      wordsTotal: words.filter((x) => x.categoryId === c.id).length,
      scenariosDone: scenarios.filter(
        (x) => x.categoryId === c.id && db.completedScenarios.includes(x.id),
      ).length,
      scenariosTotal: scenarios.filter((x) => x.categoryId === c.id).length,
    })),
  };
}

export const api = {
  getCategories: (): Promise<Category[]> => delay(categories, 100),

  getWords: (opts: { categoryId?: string; query?: string } = {}): Promise<Word[]> => {
    const q = opts.query?.trim().toLowerCase();
    return delay(
      words.filter(
        (x) =>
          (!opts.categoryId || x.categoryId === opts.categoryId) &&
          (!q ||
            x.english.toLowerCase().includes(q) ||
            (x.rohingyalish?.toLowerCase().includes(q) ?? false)),
      ),
      150,
    );
  },

  getWord: (id: string): Promise<Word | null> => delay(words.find((x) => x.id === id) ?? null, 100),

  /** Voice search: pretend we transcribed a word and return the best match. */
  searchWordByVoice: (_audioUri: string): Promise<Word[]> => delay([words[0]], 600),

  /** Speech translation. `audioUri` is the user's recording. */
  translateSpeech: (_audioUri: string, direction: Direction): Promise<TranslateResult> =>
    delay(
      {
        sourceText: direction === 'rhg-en' ? '[mock] Rohingya speech' : 'I need a doctor.',
        translatedText: mockTranslations[direction],
        direction,
        confidence: Math.random(),
        status: 'translated',
        audioUrl: null,
      },
      900,
    ),

  /** Camera/photo translation (OCR mocked). */
  translateImage: (_imageUri: string, direction: Direction): Promise<TranslateResult> =>
    delay(
      {
        sourceText: mockOcrText,
        translatedText: mockTranslations['en-rhg'],
        direction,
        confidence: 0.7,
        status: 'translated',
        audioUrl: null,
      },
      900,
    ),

  /** Mock of POST /api/pronunciation/score. Random score, flagged as not validated. */
  scorePronunciation: (wordId: string, _audioUri: string): Promise<PronunciationResult> => {
    const score = 55 + Math.floor(Math.random() * 41);
    return delay(
      {
        wordId,
        status: 'scored',
        score,
        feedback:
          score >= 80 ? 'Great job! That sounded clear.' : 'Good try. Listen once more and repeat.',
        tips: score >= 80 ? [] : ['Say it slowly, one sound at a time.'],
        validated: false,
      },
      800,
    );
  },

  getScenarios: (categoryId?: string): Promise<Scenario[]> =>
    delay(
      scenarios.filter((x) => !categoryId || x.categoryId === categoryId),
      100,
    ),

  getScenario: (id: string): Promise<Scenario | null> =>
    delay(scenarios.find((x) => x.id === id) ?? null, 100),

  getScenarioFeedback: (_audioUri: string): Promise<ScenarioFeedback> =>
    delay(
      {
        summary: 'Placeholder feedback. Real pronunciation scoring is not available yet.',
        confidence: 0.5,
        tips: ['Speak slowly and clearly.', 'Try the sentence again.'],
      },
      500,
    ),

  /** Mock of GET /api/progress. */
  getProgress: async (): Promise<ProgressSummary> => summarize(await loadDb()),

  /** Mock of POST /api/progress. Keeps the best score per word. */
  saveProgress: async (update: ProgressUpdate): Promise<ProgressSummary> => {
    const db = await loadDb();
    if (update.type === 'word') {
      db.wordScores[update.wordId] = Math.max(db.wordScores[update.wordId] ?? 0, update.score);
      db.latestScore = update.score;
    } else if (!db.completedScenarios.includes(update.scenarioId)) {
      db.completedScenarios.push(update.scenarioId);
    }
    await persist(db);
    return summarize(db);
  },

  /** Not in the backend draft yet: saved words. */
  getSavedWordIds: async (): Promise<string[]> => [...(await loadDb()).saved],

  setWordSaved: async (wordId: string, saved: boolean): Promise<void> => {
    const db = await loadDb();
    db.saved = saved ? [...new Set([...db.saved, wordId])] : db.saved.filter((id) => id !== wordId);
    await persist(db);
  },

  /** Mock of GET /api/lessons/{id}/next: first word not yet practiced. */
  getNextWord: async (categoryId?: string): Promise<Word | null> => {
    const db = await loadDb();
    const pool = words.filter((x) => !categoryId || x.categoryId === categoryId);
    return pool.find((x) => !(x.id in db.wordScores)) ?? null;
  },
};
