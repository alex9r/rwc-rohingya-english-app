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
/**
 * Backend base URL, e.g. http://localhost:8000. When unset, or when a request
 * fails, the client falls back to mockData.ts so the app always runs.
 */
const API_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, '');
const TIMEOUT_MS = 4000;

async function getJson<T>(path: string): Promise<T | null> {
  if (!API_URL) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: controller.signal });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// ---- backend response shapes (see backend/app/main.py) ----
interface ApiCategory {
  id: string;
  name: string;
  description?: string;
}
interface ApiWordSummary {
  id: string;
  english: string;
  type?: 'word' | 'phrase';
  category_id?: string;
  rohingya?: string | null;
  image_url?: string | null;
  audio_url?: string | null;
  verification_status?: string | null;
  confidence?: number | null;
  needs_review?: boolean;
}
interface ApiWordDetail {
  id: string;
  english: { term: string };
  rohingya: { text: string | null };
  category: { id: string };
  media?: { audio?: { url: string }[]; images?: { url: string }[] };
  verification: {
    status: string;
    confidence?: number | null;
    needs_review?: boolean;
  };
}

/** Backend statuses are free-form strings such as "source_attested_pending_native_review". */
function toVerification(status: string | null | undefined): Word['verification'] {
  if (status === 'verified') return 'verified';
  return status?.includes('pending') ? 'pending_review' : 'unvalidated';
}

const fromSummary = (x: ApiWordSummary): Word => ({
  id: x.id,
  categoryId: x.category_id ?? '',
  english: x.english,
  // The datasets store Latin-script Rohingya ("Rohingyalish"); native script isn't available yet.
  rohingyalish: x.rohingya ?? null,
  rohingya: null,
  imageUrl: x.image_url ?? null,
  audioUrl: x.audio_url ?? null,
  verification: toVerification(x.verification_status),
  entryType: x.type ?? 'word',
  confidence: x.confidence ?? null,
  needsReview: x.needs_review ?? true,
});

const fromDetail = (x: ApiWordDetail): Word => ({
  id: x.id,
  categoryId: x.category.id,
  english: x.english.term,
  rohingyalish: x.rohingya.text,
  rohingya: null,
  imageUrl: x.media?.images?.[0]?.url ?? null,
  audioUrl: x.media?.audio?.[0]?.url ?? null,
  verification: toVerification(x.verification.status),
  confidence: x.verification.confidence ?? null,
  needsReview: x.verification.needs_review ?? true,
});

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
  // Ignore ids saved by older mock data (e.g. removed words/scenarios).
  const wordIds = new Set(words.map((x) => x.id));
  const scenarioIds = new Set(scenarios.map((x) => x.id));
  const practiced = new Set(Object.keys(db.wordScores).filter((id) => wordIds.has(id)));
  const completed = db.completedScenarios.filter((id) => scenarioIds.has(id));
  return {
    wordsPracticed: practiced.size,
    wordsTotal: words.length,
    scenariosCompleted: completed.length,
    scenariosTotal: scenarios.length,
    latestScore: db.latestScore,
    wordScores: db.wordScores,
    completedScenarioIds: completed,
    categories: categories.map((c) => ({
      categoryId: c.id,
      name: c.name,
      wordsPracticed: words.filter((x) => x.categoryId === c.id && practiced.has(x.id)).length,
      wordsTotal: words.filter((x) => x.categoryId === c.id).length,
      scenariosDone: scenarios.filter((x) => x.categoryId === c.id && completed.includes(x.id))
        .length,
      scenariosTotal: scenarios.filter((x) => x.categoryId === c.id).length,
    })),
  };
}

export const api = {
  getCategories: async (): Promise<Category[]> => {
    const res = await getJson<{ categories: ApiCategory[] }>('/api/categories');
    if (res?.categories.length) {
      return res.categories.map((c) => ({
        id: c.id,
        name: c.name,
        description: c.description ?? '',
      }));
    }
    return delay(categories, 100);
  },

  getWords: async (opts: { categoryId?: string; query?: string } = {}): Promise<Word[]> => {
    const params = new URLSearchParams({ limit: '100' });
    if (opts.categoryId) params.set('category', opts.categoryId);
    if (opts.query?.trim()) params.set('q', opts.query.trim());
    const res = await getJson<{ words: ApiWordSummary[] }>(`/api/words?${params}`);
    if (res) return res.words.map(fromSummary);
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

  getWord: async (id: string): Promise<Word | null> => {
    const res = await getJson<ApiWordDetail>(`/api/words/${encodeURIComponent(id)}`);
    if (res) return fromDetail(res);
    return delay(words.find((x) => x.id === id) ?? null, 100);
  },

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
