import { StyleSheet, View } from 'react-native';
import { colors, radius } from '@/theme';

/** `value` is 0..1. `onGradient` switches to a white-on-glass track. */
export function ProgressBar({ value, onGradient }: { value: number; onGradient?: boolean }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(pct) }}
      style={[styles.track, onGradient && styles.trackGlass]}
    >
      <View
        style={[styles.fill, { width: `${pct}%` }, onGradient && { backgroundColor: '#FFFFFF' }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    overflow: 'hidden',
  },
  trackGlass: { backgroundColor: colors.glass },
  fill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.primary },
});
