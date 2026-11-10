import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { useRef, useState } from 'react';
import { LoadState } from '@/components/LoadState';
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
  const micLock = useRef(false);
  const requestGeneration = useRef(0);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [retryJob, setRetryJob] = useState<(() => Promise<TranslateResult>) | null>(null);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();
  const replay = useAudioPlayer(null);

  const speakResult = (r: TranslateResult) => {
    // Only read English. Do not synthesize a missing translation.
    const english = r.direction === 'rhg-en' ? r.translatedText : r.sourceText;
    if (!english?.trim()) return;
    play({
      url: null, // Backend does not identify audio language; use English TTS safely.
      fallbackText: english,
      language: 'en-US',
    });
  };

  const run = async (job: () => Promise<TranslateResult>) => {
    const generation = ++requestGeneration.current;
    setBusy(true);
    setRequestError(null);
    setRetryJob(() => job);
    try {
      const r = await job();
      if (generation !== requestGeneration.current) return;
      setResult(r);
      if (r.status === 'translated' && r.translatedText && r.confidence >= LOW_CONFIDENCE) speakResult(r);
    } catch (error) {
      if (generation !== requestGeneration.current) return;
      setResult(null);
      setRequestError(error instanceof Error ? error.message : 'Speech translation failed. Please try again.');
    } finally {
      if (generation === requestGeneration.current) setBusy(false);
    }
  };

  const onMic = async () => {
    if (busy || micLock.current) return;
    micLock.current = true;
    try {
      const wasRecording = recording;
      const uri = await toggle();
      if (!wasRecording) {
        // Do not discard previous work if permission was denied or recording failed.
        return;
      }
      if (!uri) {
        setRecordingError('Could not save recording. Please try again.');
        return;
      }
      setRecordingError(null);
      setRecordingUri(uri);
      setResult(null);
      setRequestError(null);
      setRetryJob(null);
      await run(() => api.translateSpeech(uri, direction));
    } catch (error) {
      setRecordingError(error instanceof Error ? error.message : 'Recording failed. Please try again.');
    } finally {
      micLock.current = false;
    }
  };

  const onCamera = async () => {
    setRecordingUri(null);
    setRecordingError(null);
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
    try {
      replay.pause();
      replay.replace({ uri: recordingUri });
      replay.play();
    } catch {
      Alert.alert('Could not replay recording', 'Please try again.');
    }
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
    if (busy || recording || micLock.current) return;
    ++requestGeneration.current;
    setDirection((d) => (d === 'rhg-en' ? 'en-rhg' : 'rhg-en'));
    setResult(null);
    setRecordingUri(null);
    setRecordingError(null);
    setRequestError(null);
    setRetryJob(null);
  };

  const [from, to] = LABELS[direction];
  const lowConfidence = !!result && result.status === 'translated' && result.confidence < LOW_CONFIDENCE;
  const needsRetry = !!result && (lowConfidence || result.status !== 'translated');

  return (
    <GradientScreen>
      <ScrollView
        style={styles.flex}
        contentContainerStyle={[styles.hero, { paddingTop: insets.top + spacing.xxl }]}
      >
        {recordingError && !busy && (
          <Text style={styles.recordingError}>{recordingError}</Text>
        )}
        {recording ? (
          <View style={styles.idle}><Orb active /><Text style={styles.headline}>Listening… tap again to stop</Text></View>
        ) : busy ? (
          <ActivityIndicator size="large" color="#FFFFFF" />
        ) : requestError ? (
          <LoadState error={requestError} onRetry={retryJob ? () => void run(retryJob) : undefined} />
        ) : result ? (
          <View style={styles.result}>
            <View style={styles.textSection} accessible accessibilityLabel={`You said: ${result.sourceText.trim() || 'Speech not recognized'}`}>
              <Text style={styles.sectionLabel}>You said</Text>
              <Text style={styles.source} selectable>{result.sourceText.trim() || 'Speech not recognized'}</Text>
            </View>
            <View style={styles.textSection} accessible accessibilityLabel={`Translation: ${result.translatedText?.trim() || 'Not available yet'}`}>
              <Text style={styles.sectionLabel}>Translation</Text>
              <Text style={styles.translated} selectable>
                {result.translatedText?.trim() || (result.status === 'pending_translation'
                  ? 'Translation is not ready yet. Try again later.'
                  : 'Translation not available. Try speaking again.')}
              </Text>
            </View>
            {result.status === 'translated' && <ConfidenceBadge value={result.confidence} />}
            {(result.status !== 'translated' || result.confidence < LOW_CONFIDENCE) && (
              <View style={styles.notSure}>
                <Ionicons name="alert-circle" size={22} color="#FFFFFF" />
                <Text style={styles.notSureText}>Speech may be unclear. Tap the microphone to try again, or ask someone to help.</Text>
              </View>
            )}
            {needsRetry && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Try speaking again"
                onPress={() => { setResult(null); setRequestError(null); }}
                style={styles.retryButton}
              >
                <Ionicons name="mic" size={26} color={colors.primary} />
                <Text style={styles.retryText}>Speak again</Text>
              </Pressable>
            )}
            <View style={styles.actions}>
              <IconButton
                variant="glass"
                name="volume-high"
                label="Read aloud"
                onPress={() => speakResult(result)}
                disabled={!(result.direction === 'rhg-en' ? result.translatedText : result.sourceText)?.trim()}
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
              {recording ? 'Listening… tap again to stop' : 'Tap the mic and speak'}
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
            disabled={busy || recording}
            accessibilityState={{ disabled: busy || recording }}
            style={[styles.swap, (busy || recording) && { opacity: 0.5 }]}
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
          <View accessible={false} style={styles.micArea}>
            <MicButton recording={recording} onPress={onMic} disabled={busy} />
            <Text style={styles.micCaption}>{recording ? 'Tap to stop' : 'Tap to speak'}</Text>
          </View>
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
  recordingError: { color: '#FFFFFF', textAlign: 'center', marginBottom: spacing.md },
  headline: {
    fontSize: fonts.size.xl,
    fontWeight: fonts.weight.bold,
    color: '#FFFFFF',
    textAlign: 'center',
  },
  result: { gap: spacing.lg },
  textSection: { gap: spacing.xs },
  sectionLabel: { fontSize: fonts.size.sm, fontWeight: fonts.weight.bold, color: '#FFFFFF', opacity: 0.85 },
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
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  retryButton: { minHeight: 52, borderRadius: radius.lg, paddingHorizontal: spacing.lg, backgroundColor: '#FFFFFF', flexDirection: 'row', gap: spacing.sm, alignItems: 'center', alignSelf: 'flex-start' },
  retryText: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: colors.primary },
  micArea: { alignItems: 'center', gap: spacing.xs, minWidth: 100 },
  micCaption: { fontSize: fonts.size.sm, fontWeight: fonts.weight.bold, color: colors.text },
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
