import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

/** Tap-to-start / tap-to-stop recording. `stop()` resolves with the file uri. */
export function useRecorder() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [recording, setRecording] = useState(false);

  const start = useCallback(async () => {
    const perm = await requestRecordingPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Microphone needed', 'Please allow microphone access in Settings.');
      return;
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setRecording(true);
  }, [recorder]);

  const stop = useCallback(async (): Promise<string | null> => {
    await recorder.stop();
    setRecording(false);
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    return recorder.uri;
  }, [recorder]);

  const toggle = useCallback(
    async () => (recording ? stop() : (await start(), null)),
    [recording, start, stop],
  );

  return { recording, start, stop, toggle };
}
