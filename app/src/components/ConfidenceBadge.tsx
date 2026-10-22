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
    <View
      style={[styles.badge, { backgroundColor: color }]}
      accessibilityLabel={`${label}, ${pct} percent`}
    >
      <Text style={styles.text}>
        {label} · {pct}%
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  text: { color: colors.textOnPrimary, fontSize: fonts.size.sm, fontWeight: fonts.weight.bold },
});
