/** Frontend adapter for backend-server POST /api/transcribe.
 * Configure EXPO_PUBLIC_API_BASE_URL to the reachable backend origin.
 */
export type TranscriptionResult = {
  text: string;
  confidence: number | null;
  isConfident: boolean;
  language: string | null;
  stub: boolean;
};

export class TranscriptionError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = 'TranscriptionError';
  }
}

export async function transcribeRecording(audioUri: string, language?: 'en' | 'rhg'): Promise<TranscriptionResult> {
  const base = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '');
  if (!base) throw new TranscriptionError('Transcription server is not configured.');
  if (!audioUri) throw new TranscriptionError('Record audio before transcribing.');

  const form = new FormData();
  form.append('audio', { uri: audioUri, name: 'recording.m4a', type: 'audio/mp4' } as unknown as Blob);
  if (language) form.append('language', language);

  let response: Response;
  try {
    response = await fetch(`${base}/api/transcribe`, { method: 'POST', body: form });
  } catch {
    throw new TranscriptionError('Cannot reach the transcription server. Check your connection.');
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const reason = response.status === 503
      ? 'Speech recognition is temporarily unavailable.'
      : response.status === 422
        ? 'Could not understand this recording. Please try again.'
        : response.status === 400
          ? 'This recording or language is not supported.'
          : 'Transcription failed. Please try again.';
    throw new TranscriptionError(reason, response.status);
  }
  if (!payload || typeof payload !== 'object') throw new TranscriptionError('Invalid transcription response.');
  const data = payload as Record<string, unknown>;
  if (data.status !== 'ok' || typeof data.text !== 'string') {
    throw new TranscriptionError('No usable transcription was returned.');
  }
  if (data.stub === true) {
    throw new TranscriptionError('Speech recognition is not available yet (backend stub).');
  }
  if (!data.text.trim()) throw new TranscriptionError('No speech detected. Please record again.');
  const confidence = typeof data.confidence === 'number' && Number.isFinite(data.confidence)
    ? Math.min(1, Math.max(0, data.confidence)) : null;
  return {
    text: data.text.trim(),
    confidence,
    isConfident: data.is_confident === true,
    language: typeof data.language === 'string' ? data.language : null,
    stub: false,
  };
}
