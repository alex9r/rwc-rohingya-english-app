import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';
import { promptOpenSettings } from '@/utils/permissions';

/** Tap-to-start / tap-to-stop recording. `toggle()` resolves with the file uri when it stops. */
export function useRecorder() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [recording, setRecording] = useState(false);

  const start = useCallback(async () => {
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        promptOpenSettings('Microphone needed', 'Allow microphone access to record your voice.');
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
    } catch {
      Alert.alert('Could not start recording', 'Please try again.');
    }
  }, [recorder]);

  const stop = useCallback(async (): Promise<string | null> => {
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      return recorder.uri;
    } catch {
      Alert.alert('Could not save recording', 'Please try again.');
      return null;
    } finally {
      setRecording(false);
    }
  }, [recorder]);

  const toggle = useCallback(async (): Promise<string | null> => {
    if (recording) return stop();
    await start();
    return null;
  }, [recording, start, stop]);

  return { recording, toggle };
}
