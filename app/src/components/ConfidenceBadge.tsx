import { StyleSheet, Text, View } from 'react-native';
import { colors, fonts, radius, spacing } from '@/theme';

export const LOW_CONFIDENCE = 0.5;

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const [color, label] =
    value >= 0.8
      ? [colors.confidenceHigh, 'Confident']
      : value >= LOW_CONFIDENCE
        ? [colors.confidenceMid, 'Fairly sure']
        : [colors.confidenceLow, 'Not sure'];
  return (
    <View style={styles.badge} accessibilityLabel={`${label}, ${pct} percent`}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={styles.text}>
        {label} · {pct}%
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
    backgroundColor: '#FFFFFF',
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  text: { color: colors.text, fontSize: fonts.size.sm, fontWeight: fonts.weight.bold },
});
