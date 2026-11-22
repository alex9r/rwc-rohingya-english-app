import { useAudioPlayer } from 'expo-audio';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '@/api/client';
import { davidDemoPhrases } from '@/api/davidPhrases';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { ScoreBadge } from '@/components/ScoreBadge';
import { useRecorder } from '@/hooks/useRecorder';
import { colors, fonts, radius, spacing } from '@/theme';

type Attempt = { uri: string; score: number };

/** Demo only: recordings and mock scores remain available while this screen is mounted. */
export function PhrasePractice() {
  const [index, setIndex] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [attempts, setAttempts] = useState<Record<string, Attempt>>({});
  const { recording, toggle } = useRecorder();
  const replay = useAudioPlayer(null);
  const phrase = davidDemoPhrases[index];
  const attempt = attempts[phrase.id];

  const onMic = async () => {
    if (uploading) return;
    const uri = await toggle();
    if (!uri) return;
    setUploading(true);
    try {
      await api.submitPhraseRecording(phrase.id, uri);
      // Demo score only. This number is NOT calculated from the user's speech.
      const score = 55 + Math.floor(Math.random() * 41);
      setAttempts((prev) => ({ ...prev, [phrase.id]: { uri, score } }));
    } catch {
      Alert.alert('Could not submit recording', 'Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const onReplay = () => {
    if (!attempt) return;
    try {
      replay.pause();
      replay.replace({ uri: attempt.uri });
      replay.play();
    } catch {
      Alert.alert('Could not replay recording', 'Please try recording again.');
    }
  };

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Phrase practice (demo)</Text>
      <Text style={styles.count}>Phrase {index + 1} of {davidDemoPhrases.length}</Text>
      <Text style={styles.phrase}>{phrase.text}</Text>
      <Text style={styles.note}>Tap the mic to start, then tap again to stop.</Text>
      <View style={styles.mic}>
        <MicButton recording={recording} onPress={onMic} disabled={uploading} />
      </View>
      {uploading && <Text style={styles.note}>Processing practice recording…</Text>}
      {attempt && (
        <View style={styles.result}>
          <Text style={styles.resultTitle}>My practice</Text>
          <Text style={styles.note}>Recording saved for this session</Text>
          <IconButton name="play" label="Replay my recording" onPress={onReplay} />
          <Text style={styles.resultTitle}>Demo score</Text>
          <ScoreBadge score={attempt.score} />
          <Text style={styles.warning}>
            Mock score only — randomly generated, not based on your pronunciation.
          </Text>
        </View>
      )}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Next practice phrase"
        disabled={recording || uploading}
        onPress={() => setIndex((i) => (i + 1) % davidDemoPhrases.length)}
        style={[styles.next, (recording || uploading) && { opacity: 0.5 }]}
      >
        <Text style={styles.nextText}>Next phrase</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.lg,
    marginVertical: spacing.md,
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: colors.text },
  count: { fontSize: fonts.size.sm, color: colors.primary, fontWeight: fonts.weight.bold },
  phrase: { fontSize: fonts.size.lg, color: colors.text, fontWeight: fonts.weight.bold },
  note: { fontSize: fonts.size.sm, color: colors.textMuted },
  mic: { alignItems: 'center', paddingVertical: spacing.sm },
  result: {
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
  },
  resultTitle: { fontSize: fonts.size.md, color: colors.text, fontWeight: fonts.weight.bold },
  warning: { fontSize: fonts.size.sm, color: colors.textMuted, textAlign: 'center' },
  next: { backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md, alignItems: 'center' },
  nextText: { color: '#FFFFFF', fontWeight: fonts.weight.bold },
});
