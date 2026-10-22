import { useAudioPlayer } from 'expo-audio';
import * as Speech from 'expo-speech';
import { useCallback, useEffect } from 'react';

/** Plays a URL when present; falls back to text-to-speech so mock data still "speaks". */
export function usePlayAudio() {
  const player = useAudioPlayer(null);

  useEffect(() => () => void Speech.stop(), []);

  return useCallback(
    (opts: { url?: string | null; fallbackText?: string; language?: string }) => {
      void Speech.stop();
      if (opts.url) {
        player.replace({ uri: opts.url });
        player.play();
      } else if (opts.fallbackText) {
        Speech.speak(opts.fallbackText, { language: opts.language ?? 'en-US' });
      }
    },
    [player],
  );
}
