export type Direction = 'rhg-en' | 'en-rhg';
export type VerificationStatus = 'unvalidated' | 'pending_review' | 'verified';

export interface Category {
  id: string;
  name: string;
  description: string;
}

export interface Word {
  id: string;
  categoryId: string;
  english: string;
  /** Rohingyalish (Latin) spelling. null = no translation yet; never fabricate. */
  rohingyalish: string | null;
  /** Native-script text (Hanifi Rohingya) when available. */
  rohingya: string | null;
  imageUrl: string | null;
  audioUrl: string | null;
  verification: VerificationStatus;
}

export interface TranslateResult {
  sourceText: string;
  translatedText: string | null;
  direction: Direction;
  /** 0..1 */
  confidence: number;
  status: 'translated' | 'pending_translation';
  audioUrl: string | null;
}

export interface ScenarioTurn {
  id: string;
  role: 'partner' | 'user';
  text: string;
}

export interface Scenario {
  id: string;
  categoryId: string;
  title: string;
  turns: ScenarioTurn[];
}

export interface ScenarioFeedback {
  summary: string;
  confidence: number;
  tips: string[];
}

/** Mirrors POST /api/pronunciation/score; `scoring_unavailable` = score can't be trusted. */
export interface PronunciationResult {
  wordId: string;
  status: 'scored' | 'scoring_unavailable';
  /** 0..100, null when unavailable. */
  score: number | null;
  feedback: string;
  tips: string[];
  /** false while the scoring model hasn't been validated with Rohingya/English learners. */
  validated: boolean;
}

export type ProgressUpdate =
  { type: 'word'; wordId: string; score: number } | { type: 'scenario'; scenarioId: string };

export interface CategoryProgress {
  categoryId: string;
  name: string;
  wordsPracticed: number;
  wordsTotal: number;
  scenariosDone: number;
  scenariosTotal: number;
}

/** Superset of GET /api/progress (completed_lessons, words_practiced, latest_pronunciation_score). */
export interface ProgressSummary {
  wordsPracticed: number;
  wordsTotal: number;
  scenariosCompleted: number;
  scenariosTotal: number;
  latestScore: number | null;
  /** wordId -> best score */
  wordScores: Record<string, number>;
  completedScenarioIds: string[];
  categories: CategoryProgress[];
}
