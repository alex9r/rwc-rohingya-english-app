import { useAudioPlayer } from 'expo-audio';
import * as Speech from 'expo-speech';
import { useCallback, useEffect } from 'react';

/**
 * Prefer recorded audio from the API (audioUrl); use English text-to-speech
 * only when a recording is missing. Do not silently speak a different language
 * as a substitute for an unavailable Rohingya recording.
 */
export function usePlayAudio() {
  const player = useAudioPlayer(null);

  useEffect(() => () => {
    void Speech.stop();
    player.pause();
  }, [player]);

  return useCallback(
    (opts: { url?: string | null; fallbackText?: string; language?: string; rate?: number }) => {
      void Speech.stop();
      player.pause();

      const url = opts.url?.trim();
      if (url) {
        try {
          player.replace({ uri: url });
          player.play();
        } catch (error) {
          console.warn('Could not start audio playback', error);
        }
        return;
      }

      const text = opts.fallbackText?.trim();
      if (text) {
        Speech.speak(text, { language: opts.language ?? 'en-US', rate: opts.rate });
      }
    },
    [player],
  );
}
