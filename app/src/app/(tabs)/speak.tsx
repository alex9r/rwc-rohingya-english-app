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
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { Direction, TranslateResult } from '@/api/types';
import { ConfidenceBadge, LOW_CONFIDENCE } from '@/components/ConfidenceBadge';
import { GradientScreen } from '@/components/GradientScreen';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { Orb } from '@/components/Orb';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { colors, fonts, radius, shadow, spacing, TAB_BAR_SPACE } from '@/theme';
import { promptOpenSettings } from '@/utils/permissions';

const LABELS: Record<Direction, [string, string]> = {
  'rhg-en': ['Rohingya', 'English'],
  'en-rhg': ['English', 'Rohingya'],
};

export default function SpeakScreen() {
  const insets = useSafeAreaInsets();
  const [direction, setDirection] = useState<Direction>('rhg-en');
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();
  const replay = useAudioPlayer(null);

  const speakResult = (r: TranslateResult) => {
    // Read the English side aloud (TTS fallback until backend audio exists).
    const english = r.direction === 'rhg-en' ? r.translatedText : r.sourceText;
    play({ url: r.direction === 'rhg-en' ? r.audioUrl : null, fallbackText: english ?? undefined });
  };

  const run = async (job: () => Promise<TranslateResult>) => {
    setBusy(true);
    try {
      const r = await job();
      setResult(r);
      speakResult(r);
    } catch {
      Alert.alert('Translation failed', 'Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  const onMic = async () => {
    const uri = await toggle();
    if (!uri) return;
    setRecordingUri(uri);
    await run(() => api.translateSpeech(uri, direction));
  };

  const onCamera = async () => {
    let perm = await ImagePicker.getCameraPermissionsAsync();
    if (!perm.granted) {
      if (!perm.canAskAgain) {
        return promptOpenSettings(
          'Camera needed',
          'Allow camera access to translate text in photos.',
        );
      }
      perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) return;
    }
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'] });
    if (shot.canceled) return;
    await run(() => api.translateImage(shot.assets[0].uri, direction));
  };

  const onReplay = () => {
    if (!recordingUri) return;
    replay.replace({ uri: recordingUri });
    replay.play();
  };

  const onSave = () => {
    if (!recordingUri) return;
    try {
      new File(recordingUri).copy(new File(Paths.document, `recording-${Date.now()}.m4a`));
      Alert.alert('Saved', 'Recording saved on this device.');
    } catch {
      Alert.alert('Could not save', 'Please try again.');
    }
  };

  const swap = () => {
    setDirection((d) => (d === 'rhg-en' ? 'en-rhg' : 'rhg-en'));
    setResult(null);
  };

  const [from, to] = LABELS[direction];

  return (
    <GradientScreen>
      <ScrollView
        style={styles.flex}
        contentContainerStyle={[styles.hero, { paddingTop: insets.top + spacing.xxl }]}
      >
        {busy ? (
          <ActivityIndicator size="large" color="#FFFFFF" />
        ) : result ? (
          <View style={styles.result}>
            <Text style={styles.source}>{result.sourceText}</Text>
            <Text style={styles.translated}>{result.translatedText ?? 'No translation yet'}</Text>
            <ConfidenceBadge value={result.confidence} />
            {result.confidence < LOW_CONFIDENCE && (
              <View style={styles.notSure}>
                <Ionicons name="alert-circle" size={22} color="#FFFFFF" />
                <Text style={styles.notSureText}>Not sure. Try again or ask someone to help.</Text>
              </View>
            )}
            <View style={styles.actions}>
              <IconButton
                variant="glass"
                name="volume-high"
                label="Read aloud"
                onPress={() => speakResult(result)}
              />
              <IconButton
                variant="glass"
                name="play"
                label="Replay recording"
                onPress={onReplay}
                disabled={!recordingUri}
              />
              <IconButton
                variant="glass"
                name="download-outline"
                label="Save recording"
                onPress={onSave}
                disabled={!recordingUri}
              />
            </View>
          </View>
        ) : (
          <View style={styles.idle}>
            <Orb active={recording} />
            <Text style={styles.headline}>
              {recording ? 'Listening…' : 'Tap the mic and speak'}
            </Text>
          </View>
        )}
      </ScrollView>

      <View style={[styles.card, { marginBottom: insets.bottom + TAB_BAR_SPACE }]}>
        <View style={styles.langRow}>
          <Text style={styles.lang}>{from}</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Swap languages. Now ${from} to ${to}`}
            onPress={swap}
            style={styles.swap}
          >
            <Ionicons name="swap-horizontal" size={24} color={colors.primary} />
          </Pressable>
          <Text style={styles.lang}>{to}</Text>
        </View>
        <View style={styles.controls}>
          <IconButton
            name="camera"
            label="Translate text from a photo"
            onPress={onCamera}
            disabled={busy || recording}
          />
          <MicButton recording={recording} onPress={onMic} disabled={busy} />
          <View style={styles.spacer} />
        </View>
      </View>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  hero: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
  },
  idle: { alignItems: 'center', gap: spacing.xl },
  headline: {
    fontSize: fonts.size.xl,
    fontWeight: fonts.weight.bold,
    color: '#FFFFFF',
    textAlign: 'center',
  },
  result: { gap: spacing.lg },
  source: {
    fontSize: fonts.size.lg,
    color: '#FFFFFF',
    opacity: 0.9,
    fontWeight: fonts.weight.bold,
  },
  translated: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  notSure: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  notSureText: {
    flex: 1,
    fontSize: fonts.size.md,
    fontWeight: fonts.weight.bold,
    color: '#FFFFFF',
  },
  actions: { flexDirection: 'row', gap: spacing.md },
  card: {
    marginHorizontal: spacing.lg,
    padding: spacing.lg,
    gap: spacing.xl,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    ...shadow.card,
  },
  langRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  lang: {
    flex: 1,
    textAlign: 'center',
    fontSize: fonts.size.lg,
    fontWeight: fonts.weight.bold,
    color: colors.text,
  },
  swap: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  spacer: { width: 48 },
});
