import { StyleSheet, Text, View } from 'react-native';
import { colors, fonts, spacing } from '@/theme';

export function scoreBand(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Great!', color: colors.confidenceHigh };
  if (score >= 60) return { label: 'Good try', color: colors.confidenceMid };
  return { label: 'Keep practicing', color: colors.confidenceLow };
}

export function ScoreBadge({ score }: { score: number }) {
  const { label, color } = scoreBand(score);
  return (
    <View style={styles.wrap} accessibilityLabel={`${label}. Score ${score} out of 100`}>
      <View style={[styles.ring, { borderColor: color }]}>
        <Text style={styles.score}>{score}</Text>
      </View>
      <Text style={[styles.label, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: spacing.sm },
  ring: {
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  score: { fontSize: fonts.size.xl, fontWeight: fonts.weight.bold, color: colors.text },
  label: { fontSize: fonts.size.lg, fontWeight: fonts.weight.bold },
});
