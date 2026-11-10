import { Ionicons } from '@expo/vector-icons';
import { useAudioPlayer } from 'expo-audio';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { Scenario, ScenarioFeedback, ScenarioTurn } from '@/api/types';
import { BackButton } from '@/components/BackButton';
import { ConfidenceBadge } from '@/components/ConfidenceBadge';
import { GradientScreen } from '@/components/GradientScreen';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { LoadState } from '@/components/LoadState';
import { Sheet } from '@/components/Sheet';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { useAppState } from '@/state/AppState';
import { colors, fonts, radius, shadow, spacing, TAB_BAR_SPACE } from '@/theme';

type Item =
  | ScenarioTurn
  | { id: string; role: 'user'; text: string; recordingUri: string }
  | { id: string; role: 'feedback'; feedback: ScenarioFeedback }
  | { id: string; role: 'complete' };

export default function ScenarioChat() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { recordScenarioComplete } = useAppState();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  // Retry is a user event, so resetting request state here is safe under
  // react-hooks/set-state-in-effect and makes the loading indicator visible.
  const retryLoad = () => {
    setLoading(true);
    setLoadError(null);
    setRetryKey((n) => n + 1);
  };
  const [items, setItems] = useState<Item[]>([]);
  const list = useRef<FlatList<Item>>(null);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();
  const replay = useAudioPlayer(null);
  const [busy, setBusy] = useState(false);

  const onReplay = useCallback((uri: string) => {
    try {
      replay.pause();
      replay.replace({ uri });
      replay.play();
    } catch {
      Alert.alert('Could not replay recording', 'Please try again.');
    }
  }, [replay]);

  useEffect(() => {
    let live = true;
    api.getScenario(id)
      .then((s) => {
        if (!live) return;
        if (!s || !s.turns.length) setLoadError('Scenario not found.');
        else { setScenario(s); setItems([s.turns[0]]); setLoadError(null); }
      })
      .catch(() => { if (live) setLoadError('Could not load this scenario.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [id, retryKey]);

  const complete = !!items.find((i) => i.role === 'complete');
  // Current step = how many partner prompts have been shown so far.
  const step = items.filter((i) => i.role === 'partner').length;

  const onMic = async () => {
    const uri = await toggle();
    if (!uri || !scenario || busy) return;
    setBusy(true);
    try {
      const feedback = await api.getScenarioFeedback(uri);
      const next = scenario.turns[step];
      setItems((prev) => [
        ...prev,
        { id: `u${prev.length}`, role: 'user', text: 'Your recording', recordingUri: uri },
        { id: `f${prev.length}`, role: 'feedback', feedback },
        next ?? { id: 'complete', role: 'complete' },
      ]);
      if (!next) await recordScenarioComplete(scenario.id);
    } catch {
      Alert.alert('Could not get feedback', 'Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const renderItem = useCallback(
    ({ item }: { item: Item }) => {
      if (item.role === 'complete') {
        return (
          <View style={styles.complete}>
            <Ionicons name="trophy" size={32} color={colors.confidenceMid} />
            <Text style={styles.completeTitle}>Scenario complete!</Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.replace('/scenario')}
              style={styles.completeBtn}
            >
              <Text style={styles.completeBtnText}>More scenarios</Text>
            </Pressable>
          </View>
        );
      }
      if (item.role === 'feedback') {
        return (
          <View style={styles.feedback}>
            <Text style={styles.feedbackTitle}>Feedback (placeholder)</Text>
            <ConfidenceBadge value={item.feedback.confidence} />
            <Text style={styles.feedbackText}>{item.feedback.summary}</Text>
            {item.feedback.tips.map((t) => (
              <Text key={t} style={styles.feedbackText}>
                • {t}
              </Text>
            ))}
          </View>
        );
      }
      const user = item.role === 'user';
      return (
        <View style={[styles.bubble, user ? styles.user : styles.partner]}>
          <Text style={[styles.bubbleText, user && styles.userText]}>{item.text}</Text>
          {user && 'recordingUri' in item && (
            <IconButton
              name="play"
              label="Replay my recording"
              size={20}
              onPress={() => onReplay(item.recordingUri)}
            />
          )}
          {!user && (
            <IconButton
              name="volume-high"
              label="Play message"
              size={20}
              onPress={() => play({ fallbackText: item.text })}
            />
          )}
        </View>
      );
    },
    [onReplay, play, router],
  );

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <BackButton fallback="/scenario" />
        <Text style={styles.title}>{scenario?.title ?? 'Scenario'}</Text>
        {scenario && (
          <Text style={styles.sub}>
            Step {step} of {scenario.turns.length}
          </Text>
        )}
      </View>
      <Sheet>
        {loading || loadError ? (
          <LoadState loading={loading} error={loadError} onRetry={retryLoad} message="Loading scenario…" />
        ) : (
        <>
        <FlatList
          ref={list}
          style={styles.flex}
          data={items}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
          contentContainerStyle={styles.list}
        />
        <View style={[styles.micBar, { paddingBottom: insets.bottom + TAB_BAR_SPACE }]}>
          <MicButton recording={recording} onPress={onMic} disabled={complete || busy} />
        </View>
        </>
        )}
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
    gap: spacing.md,
    alignItems: 'flex-start',
  },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  sub: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: '#FFFFFF', opacity: 0.9 },
  list: { padding: spacing.xl, gap: spacing.lg },
  bubble: {
    maxWidth: '85%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: radius.md,
  },
  partner: { alignSelf: 'flex-start', backgroundColor: colors.primarySoft },
  user: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  bubbleText: { flexShrink: 1, fontSize: fonts.size.md, color: colors.text },
  userText: { color: '#FFFFFF' },
  feedback: {
    gap: spacing.sm,
    padding: spacing.xl,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.card,
  },
  feedbackTitle: {
    fontSize: fonts.size.md,
    fontWeight: fonts.weight.bold,
    color: colors.primaryDark,
  },
  feedbackText: { fontSize: fonts.size.sm, color: colors.text },
  complete: {
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
  },
  completeTitle: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold, color: colors.text },
  completeBtn: {
    minHeight: 48,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  completeBtnText: { fontSize: fonts.size.md, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
  micBar: {
    alignItems: 'center',
    paddingTop: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
