import { useEffect, useRef, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { api } from '@/api/client';
import type { ScenarioFeedback, ScenarioTurn } from '@/api/types';
import { ConfidenceBadge } from '@/components/ConfidenceBadge';
import { IconButton } from '@/components/IconButton';
import { MicButton } from '@/components/MicButton';
import { usePlayAudio } from '@/hooks/usePlayAudio';
import { useRecorder } from '@/hooks/useRecorder';
import { colors, fonts, radius, spacing } from '@/theme';

type Item = ScenarioTurn | { id: string; role: 'feedback'; feedback: ScenarioFeedback };

export default function ScenarioScreen() {
  const [title, setTitle] = useState('');
  const [partnerTurns, setPartnerTurns] = useState<ScenarioTurn[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const turnIndex = useRef(0);
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

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      <FlatList
        data={items}
        keyExtractor={(i) => i.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) =>
          item.role === 'feedback' ? (
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
          ) : (
            <View style={[styles.bubble, item.role === 'user' ? styles.user : styles.partner]}>
              <Text
                style={[styles.bubbleText, item.role === 'user' && { color: colors.textOnPrimary }]}
              >
                {item.text}
              </Text>
              {item.role === 'partner' && (
                <IconButton
                  name="volume-high"
                  label="Play message"
                  size={20}
                  onPress={() => play({ fallbackText: item.text })}
                />
              )}
            </View>
          )
        }
      />
      <View style={styles.micBar}>
        <MicButton recording={recording} onPress={onMic} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: spacing.xxl * 1.5 },
  title: {
    fontSize: fonts.size.xl,
    fontWeight: fonts.weight.bold,
    color: colors.text,
    paddingHorizontal: spacing.lg,
  },
  list: { padding: spacing.lg, gap: spacing.md },
  bubble: {
    maxWidth: '85%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.lg,
  },
  partner: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  user: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  bubbleText: { flexShrink: 1, fontSize: fonts.size.md, color: colors.text },
  feedback: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  feedbackTitle: {
    fontWeight: fonts.weight.bold,
    color: colors.primaryDark,
    fontSize: fonts.size.md,
  },
  feedbackText: { color: colors.text, fontSize: fonts.size.sm },
  micBar: { alignItems: 'center', paddingVertical: spacing.lg, backgroundColor: colors.surface },
});
