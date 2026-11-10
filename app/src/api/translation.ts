import type { Direction, TranslateResult } from './types';

/** Matches backend-server: POST /api/translate. */
type BackendTranslation = {
  source_text?: unknown;
  translated_text?: unknown;
  status?: unknown;
  confidence?: unknown;
  audio_url?: unknown;
  stub?: unknown;
};

export class TranslationApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TranslationApiError';
  }
}

export async function translateText(text: string, direction: Direction): Promise<TranslateResult> {
  const sourceText = text.trim();
  if (!sourceText) throw new TranslationApiError('No recognized speech to translate.');

  const baseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '');
  if (!baseUrl) throw new TranslationApiError('Backend URL is not configured.');
  const [sourceLanguage, targetLanguage] = direction === 'rhg-en' ? ['rhg', 'en'] : ['en', 'rhg'];

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: sourceText,
        source_language: sourceLanguage,
        target_language: targetLanguage,
        preferred_script: 'Latin',
      }),
    });
  } catch {
    throw new TranslationApiError('Cannot reach the translation service. Check your connection.');
  }

  if (!response.ok) {
    throw new TranslationApiError(
      response.status === 422 ? 'The translation service could not process this text.' :
      response.status >= 500 ? 'Translation service is temporarily unavailable.' :
      `Translation request failed (${response.status}).`,
    );
  }

  let data: BackendTranslation;
  try {
    data = (await response.json()) as BackendTranslation;
  } catch {
    throw new TranslationApiError('Translation service returned an invalid response.');
  }
  if (!data || typeof data !== 'object' ||
      (data.status !== 'translated' && data.status !== 'pending_translation')) {
    throw new TranslationApiError('Translation service returned an unexpected status.');
  }

  // Never present a stub or missing translation as a real translated result.
  const translatedText = data.stub === true || data.status !== 'translated'
    ? null
    : typeof data.translated_text === 'string' && data.translated_text.trim()
      ? data.translated_text.trim()
      : null;
  const rawConfidence = data.confidence;
  const confidence = typeof rawConfidence === 'number' && Number.isFinite(rawConfidence)
    ? Math.max(0, Math.min(1, rawConfidence)) : 0;

  return {
    sourceText,
    translatedText,
    direction,
    confidence: translatedText ? confidence : 0,
    status: translatedText ? 'translated' : 'pending_translation',
    audioUrl: translatedText && typeof data.audio_url === 'string' ? data.audio_url : null,
  };
}
