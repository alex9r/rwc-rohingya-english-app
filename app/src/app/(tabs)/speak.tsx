import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { api } from '@/api/client';
import type { Direction, TranslateResult } from '@/api/types';
import { ConfidenceBadge, LOW_CONFIDENCE } from '@/components/ConfidenceBadge';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { colors, fonts, radius, spacing } from '@/theme';

const LABELS: Record<Direction, [string, string]> = {
  'rhg-en': ['Rohingya', 'English'],
  'en-rhg': ['English', 'Rohingya'],
};

export default function SpeakScreen() {
  const [direction, setDirection] = useState<Direction>('rhg-en');
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();
  const replay = useAudioPlayer(null);

  const speakResult = (r: TranslateResult) => {
    // Read the English side aloud (mock/TTS fallback until backend audio exists).
    const english = r.direction === 'rhg-en' ? r.translatedText : r.sourceText;
    play({ url: r.direction === 'rhg-en' ? r.audioUrl : null, fallbackText: english ?? undefined });
  };

  const onMic = async () => {
    const uri = await toggle();
    if (!uri) return;
    setRecordingUri(uri);
    setBusy(true);
    try {
      const r = await api.translateSpeech(uri, direction);
      setResult(r);
      speakResult(r);
    } finally {
      setBusy(false);
    }
  };

  const onCamera = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted)
      return Alert.alert('Camera needed', 'Please allow camera access in Settings.');
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'] });
    if (shot.canceled) return;
    setBusy(true);
    try {
      setResult(await api.translateImage(shot.assets[0].uri, direction));
    } finally {
      setBusy(false);
    }
  };

  const onReplay = () => {
    if (!recordingUri) return;
    replay.replace({ uri: recordingUri });
    replay.play();
  };

  const onSave = () => {
    if (!recordingUri) return;
    try {
      const dest = new File(Paths.document, `recording-${Date.now()}.m4a`);
      new File(recordingUri).copy(dest);
      Alert.alert('Saved', 'Recording saved on this device.');
    } catch {
      Alert.alert('Could not save', 'Please try again.');
    }
  };

  const [from, to] = LABELS[direction];

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.langRow}>
        <Text style={styles.lang}>{from}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Swap languages"
          onPress={() => {
            setDirection(direction === 'rhg-en' ? 'en-rhg' : 'rhg-en');
            setResult(null);
          }}
          style={styles.swap}
        >
          <Ionicons name="swap-horizontal" size={26} color={colors.primary} />
        </Pressable>
        <Text style={styles.lang}>{to}</Text>
      </View>

      <View style={styles.resultCard}>
        {busy ? (
          <ActivityIndicator size="large" color={colors.primary} />
        ) : result ? (
          <>
            <Text style={styles.source}>{result.sourceText}</Text>
            <Text style={styles.translated}>{result.translatedText ?? 'No translation yet'}</Text>
            <ConfidenceBadge value={result.confidence} />
            {result.confidence < LOW_CONFIDENCE && (
              <Text style={styles.notSure}>
                I am not sure. Please try again or ask someone to help.
              </Text>
            )}
            <View style={styles.actions}>
              <IconButton
                name="volume-high"
                label="Read aloud"
                onPress={() => speakResult(result)}
              />
              <IconButton
                name="play"
                label="Replay recording"
                onPress={onReplay}
                disabled={!recordingUri}
              />
              <IconButton
                name="download-outline"
                label="Save recording"
                onPress={onSave}
                disabled={!recordingUri}
              />
            </View>
          </>
        ) : (
          <Text style={styles.hint}>Tap the microphone, speak, then tap again to stop.</Text>
        )}
      </View>

      <View style={styles.bottom}>
        <IconButton
          name="camera"
          label="Translate text from a photo"
          onPress={onCamera}
          size={30}
        />
        <MicButton recording={recording} onPress={onMic} disabled={busy} size={104} />
        <View style={{ width: 48 }} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: spacing.lg, gap: spacing.xl, paddingTop: spacing.xxl * 1.5 },
  langRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.lg,
  },
  lang: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: colors.text },
  swap: { padding: spacing.md, backgroundColor: colors.primarySoft, borderRadius: radius.pill },
  resultCard: {
    minHeight: 220,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: spacing.md,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  source: { fontSize: fonts.size.md, color: colors.textMuted },
  translated: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: colors.text },
  notSure: { fontSize: fonts.size.md, color: colors.confidenceLow },
  hint: { fontSize: fonts.size.md, color: colors.textMuted, textAlign: 'center' },
  actions: { flexDirection: 'row', gap: spacing.md },
  bottom: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
  },
});
