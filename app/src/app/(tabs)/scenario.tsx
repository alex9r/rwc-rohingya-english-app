import { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '@/api/client';
import type { ScenarioFeedback, ScenarioTurn } from '@/api/types';
import { ConfidenceBadge } from '@/components/ConfidenceBadge';
import { GradientScreen } from '@/components/GradientScreen';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { Sheet } from '@/components/Sheet';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { colors, fonts, radius, shadow, spacing, TAB_BAR_SPACE } from '@/theme';

type Item = ScenarioTurn | { id: string; role: 'feedback'; feedback: ScenarioFeedback };

export default function ScenarioScreen() {
  const insets = useSafeAreaInsets();
  const [title, setTitle] = useState('');
  const [partnerTurns, setPartnerTurns] = useState<ScenarioTurn[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const turnIndex = useRef(0);
  const list = useRef<FlatList<Item>>(null);
  const { recording, toggle } = useRecorder();
  const play = usePlayAudio();

  useEffect(() => {
    api.getScenario().then((s) => {
      setTitle(s.title);
      setPartnerTurns(s.turns);
      setItems([s.turns[0]]);
      turnIndex.current = 1;
    });
  }, []);

  const onMic = async () => {
    const uri = await toggle();
    if (!uri) return;
    const feedback = await api.getScenarioFeedback(uri);
    const next = partnerTurns[turnIndex.current];
    turnIndex.current += 1;
    setItems((prev) => [
      ...prev,
      { id: `u${prev.length}`, role: 'user', text: '[mock] your spoken answer' },
      { id: `f${prev.length}`, role: 'feedback', feedback },
      ...(next ? [next] : []),
    ]);
  };

  const renderItem = useCallback(
    ({ item }: { item: Item }) => {
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
    [play],
  );

  return (
    <GradientScreen>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.title}>{title || 'Scenario'}</Text>
      </View>
      <Sheet>
        <FlatList
          ref={list}
          data={items}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
          contentContainerStyle={styles.list}
        />
        <View style={[styles.micBar, { paddingBottom: insets.bottom + TAB_BAR_SPACE }]}>
          <MicButton recording={recording} onPress={onMic} />
        </View>
      </Sheet>
    </GradientScreen>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl },
  title: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: '#FFFFFF' },
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
  micBar: {
    alignItems: 'center',
    paddingTop: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
