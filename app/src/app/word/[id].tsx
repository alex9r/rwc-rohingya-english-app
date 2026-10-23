import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer } from 'expo-audio';
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { PronunciationResult, Word } from '@/api/types';
import { BackButton } from '@/components/BackButton';
import { GradientScreen } from '@/components/GradientScreen';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { ScoreBadge } from '@/components/ScoreBadge';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { useAppState } from '@/state/AppState';
import { colors, fonts, radius, shadow, spacing } from '@/theme';

/** Word detail + pronunciation practice: hear it, say it, get a score. */
export default function WordPractice() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const { saved, toggleSaved, progress, recordWordPractice } = useAppState();
  const [word, setWord] = useState<Word | null>(null);
  const [result, setResult] = useState<PronunciationResult | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();
  const replay = useAudioPlayer(null);

  useEffect(() => {
    api.getWord(id).then(setWord);
  }, [id]);

  const onMic = async () => {
    const uri = await toggle();
    if (!uri || !word) return;
    setRecordingUri(uri);
    setBusy(true);
    try {
      const r = await api.scorePronunciation(word.id, uri);
      setResult(r);
      if (r.status === 'scored' && r.score !== null) await recordWordPractice(word.id, r.score);
    } catch {
      Alert.alert('Could not score that', 'Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  const onReplay = () => {
    if (!recordingUri) return;
    replay.replace({ uri: recordingUri });
    replay.play();
  };

  const best = word ? progress?.wordScores[word.id] : undefined;

  return (
    <GradientScreen>
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl },
        ]}
      >
        <View style={styles.topRow}>
          <BackButton fallback="/words" icon="close" />
          {word && (
            <IconButton
              variant="glass"
              name={saved.has(word.id) ? 'bookmark' : 'bookmark-outline'}
              label={saved.has(word.id) ? 'Unsave word' : 'Save word'}
              active={saved.has(word.id)}
              onPress={() => toggleSaved(word.id)}
            />
          )}
        </View>

        {!word ? (
          <ActivityIndicator size="large" color="#FFFFFF" style={styles.loading} />
        ) : (
          <>
            <View style={styles.hero}>
              <Text style={styles.english}>{word.english}</Text>
              <Text style={styles.rohingya}>
                {word.rohingya ?? word.rohingyalish ?? 'Not translated yet'}
              </Text>
              <View style={styles.hearRow}>
                <IconButton
                  variant="glass"
                  name="volume-high"
                  label={`Hear ${word.english}`}
                  onPress={() => play({ url: word.audioUrl, fallbackText: word.english })}
                />
                <IconButton
                  variant="glass"
                  name="hourglass-outline"
                  label={`Hear ${word.english} slowly`}
                  onPress={() => play({ fallbackText: word.english, rate: 0.5 })}
                />
              </View>
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Say it in English</Text>
              {best !== undefined && <Text style={styles.best}>Your best score: {best}</Text>}

              {busy ? (
                <ActivityIndicator size="large" color={colors.primary} style={styles.loading} />
              ) : result ? (
                <View style={styles.result}>
                  {result.status === 'scored' && result.score !== null ? (
                    <ScoreBadge score={result.score} />
                  ) : (
                    <View style={styles.unavailable}>
                      <Ionicons name="help-circle" size={32} color={colors.textMuted} />
                      <Text style={styles.feedback}>
                        We can’t score this one yet. Keep practicing by listening and repeating.
                      </Text>
                    </View>
                  )}
                  {result.status === 'scored' && (
                    <Text style={styles.feedback}>{result.feedback}</Text>
                  )}
                  {result.tips.map((t) => (
                    <Text key={t} style={styles.tip}>
                      • {t}
                    </Text>
                  ))}
                  {!result.validated && (
                    <Text style={styles.note}>Placeholder score. Scoring isn’t validated yet.</Text>
                  )}
                  <IconButton
                    name="play"
                    label="Replay my recording"
                    onPress={onReplay}
                    disabled={!recordingUri}
                  />
                </View>
              ) : (
                <Text style={styles.hint}>
                  Tap the mic, say “{word.english}”, then tap again to stop.
                </Text>
              )}

              <View style={styles.micWrap}>
                <MicButton recording={recording} onPress={onMic} disabled={busy} />
              </View>
            </View>
          </>
        )}
      </ScrollView>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 1, paddingHorizontal: spacing.xl, gap: spacing.xl },
  topRow: { flexDirection: 'row', justifyContent: 'space-between' },
  loading: { marginVertical: spacing.xl },
  hero: { alignItems: 'center', gap: spacing.md, paddingVertical: spacing.lg },
  english: {
    fontSize: fonts.size.xl,
    fontWeight: fonts.weight.bold,
    color: '#FFFFFF',
    textAlign: 'center',
  },
  rohingya: {
    fontSize: fonts.size.lg,
    fontWeight: fonts.weight.bold,
    color: '#FFFFFF',
    opacity: 0.9,
    textAlign: 'center',
  },
  hearRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
  card: {
    alignItems: 'center',
    gap: spacing.lg,
    padding: spacing.xl,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    ...shadow.card,
  },
  cardTitle: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: colors.text },
  best: { fontSize: fonts.size.sm, color: colors.textMuted },
  hint: { fontSize: fonts.size.md, color: colors.textMuted, textAlign: 'center' },
  result: { alignItems: 'center', gap: spacing.md },
  unavailable: { alignItems: 'center', gap: spacing.sm },
  feedback: { fontSize: fonts.size.md, color: colors.text, textAlign: 'center' },
  tip: { fontSize: fonts.size.sm, color: colors.textMuted },
  note: {
    fontSize: fonts.size.sm,
    color: colors.textMuted,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  micWrap: { marginTop: spacing.sm },
});
