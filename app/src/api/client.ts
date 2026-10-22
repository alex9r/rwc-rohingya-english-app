import { categories, mockOcrText, mockTranslations, scenarios, words } from './mockData';
import type {
  Category,
  Direction,
  Scenario,
  ScenarioFeedback,
  TranslateResult,
  Word,
} from './types';

/**
 * Mock API client. Mirrors the shape of the planned backend but reads from
 * mockData.ts. Swap the bodies for fetch() calls once the backend exists.
 */
const delay = <T>(value: T, ms = 400): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

export const api = {
  getCategories: (): Promise<Category[]> => delay(categories, 150),

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
      200,
    );
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

  getScenario: (id = 'doctor_visit'): Promise<Scenario> =>
    delay(scenarios.find((s) => s.id === id) ?? scenarios[0], 200),

  getScenarioFeedback: (_audioUri: string): Promise<ScenarioFeedback> =>
    delay(
      {
        summary: 'Placeholder feedback. Real pronunciation scoring is not available yet.',
        confidence: 0.5,
        tips: ['Speak slowly and clearly.', 'Try the sentence again.'],
      },
      500,
    ),
};
