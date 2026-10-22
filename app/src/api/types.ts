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
  title: string;
  turns: ScenarioTurn[];
}

export interface ScenarioFeedback {
  summary: string;
  confidence: number;
  tips: string[];
}
